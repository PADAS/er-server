import csv
import datetime
import json
import logging
import re
import urllib

import dateutil.parser
import pytz
from kombu import exceptions

import django
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Q, Window
from django.db.models.functions import FirstValue, RowNumber
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.exceptions import (APIException, ParseError,
                                       PermissionDenied, ValidationError)
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response

import utils
from das_server import celery
from das_server.views import CustomSchema
from observations import kmlutils, models, serializers
from observations.filters import (SubjectObjectPermissionsFilter,
                                  create_gp_filter_class)
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from observations.permissions import StandardObjectPermissions
from observations.serializers import (SubjectSourceSerializer,
                                      TrackLimitSerializer)
from observations.tasks import handle_outbox_message, process_gpxdata_api
from observations.utils import (VIEW_OBSERVATION_PERMS, VIEW_SUBJECT_PERMS,
                                VIEW_SUBJECTGROUP_PERMS,
                                calculate_subject_view_window,
                                check_to_include_inactive_subjects, dateparse,
                                get_minimum_allowed_age, parse_comma)
from utils import add_base_url
from utils.drf import (OptionalResultsSetPagination,
                       StandardResultsSetCursorPagination,
                       StandardResultsSetGeoJsonPagination,
                       StandardResultsSetPagination)
from utils.json import (ExtendedGEOJSONRenderer, parse_bool,
                        zeroout_microseconds)

logger = logging.getLogger(__name__)


def get_track_days():
    try:
        days = int(settings.SHOW_TRACK_DAYS)
    except AttributeError:
        days = 16
    return datetime.timedelta(days=days)


ONE_YEAR = datetime.timedelta(days=365)


def include_stationary_subjects_on_map():
    return parse_bool(getattr(settings, 'SHOW_STATIONARY_SUBJECTS_ON_MAP', True))


current_tz_name = timezone.get_current_timezone_name()
current_tz = pytz.timezone(current_tz_name)
current_date = datetime.datetime.utcnow().astimezone(current_tz)
tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
tz_offset = 'GMT' + ('+' if tz_difference >= 0 else '') + str(int(tz_difference)) + \
            ':' + str(int((tz_difference - int(tz_difference)) * 60))


def default_since():
    """default value for since
    last days is the default
    """
    return datetime.datetime.now(pytz.utc) - get_track_days()


def check_valid_date_string(date_str, parameter_name):
    if date_str:
        try:
            result = dateparse(date_str)
        except ValueError:
            raise ValueError(
                f'Invalid value for {parameter_name}: "{date_str}"')
        else:
            return True, result
    else:
        return False, None


def get_subjects_with_observations_in_daterange(start_date=None, end_date=None):
    observations_qs = models.Observation.objects.all()

    if start_date and end_date:
        observations_qs = observations_qs.filter(
            Q(recorded_at__range=(start_date, end_date)))
    elif start_date:
        observations_qs = observations_qs.filter(
            Q(recorded_at__gte=start_date))
    elif end_date:
        observations_qs = observations_qs.filter(Q(recorded_at__lte=end_date))

    subject_id_values = observations_qs.distinct(
        'source__subjectsource__subject').order_by(
        'source__subjectsource__subject_id').values(
        'source__subjectsource__subject_id')

    subject_ids = [str(i['source__subjectsource__subject_id']) for i in
                   subject_id_values if i['source__subjectsource__subject_id']]

    return models.Subject.objects.filter(id__in=subject_ids)


class UnauthorizedView(APIException):
    """
    User does not have view permission, return empty data
    """
    status_code = 200
    default_detail = {"data": []}


class RegionsView(generics.ListAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class SubjectGroupsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [{
                'name': 'include_hidden',
                'in': 'query',
                'description': 'If true, return all subject groups including hidden groups. Default is false.'},
                {
                'name': 'isvisible',
                'in': 'query',
                'description': 'Return only visible groups by default. If isvisible=false then return only hidden groups. see include_hidden'},
                {
                'name': 'include_inactive',
                'in': 'query',
                'description': 'Include inactive subjects in subject group list.'},
                {
                'name': 'flat',
                'in': 'query',
                'description': 'flatten the list of groups returned, no nested parent/child'
            },
                {
                'name': 'group_name',
                'in': 'query',
                'description': 'find subject groups with this name'
            }
            ]
            operation['parameters'].extend(query_params)
        return operation


class InactiveSubjectsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = {
                'name': 'include_inactive',
                'in': 'query',
                'description': 'Include inactive subjects in list.'}

            operation['parameters'].append(query_params)
        return operation


class RegionView(generics.RetrieveAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class SubjectGroupsView(generics.ListAPIView, TwoWaySubjectSourceMixin):
    """
    Returns all subjectgroups in the system.
    """
    serializer_class = serializers.create_sg_serializer('subjectgs', models.SubjectGroup,
                                                        serializers.SubjectSerializer)
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (create_gp_filter_class('subjectgf',
                                              ('observations.view_subjectgroup',),
                                              models.SubjectGroup),)
    schema = SubjectGroupsViewSchema()

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_SUBJECTGROUP_PERMS):
            raise UnauthorizedView

        qparams = self.request.query_params
        if parse_bool(qparams.get('flat')):
            queryset = models.SubjectGroup.objects.all()
        else:
            queryset = models.SubjectGroup.objects.get_non_cyclic_subjectgroups()

        if qparams.get('group_name'):
            queryset = queryset.by_name_search(qparams.get('group_name'))

        queryset = queryset.order_by('name')
        self._get_two_way_sources(queryset)
        return queryset

    def get_serializer_class(self):
        qparams = self.request.query_params
        include_subgroups = not parse_bool(qparams.get('flat'))
        return serializers.create_sg_serializer('subjectgs', models.SubjectGroup,
                                                serializers.SubjectSerializer, include_subgroups)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['render_last_location'] = True
        context['request'] = self.request
        context['two_way_subject_sources'] = self.two_way_subject_sources

        return context


class SubjectGroupView(generics.RetrieveAPIView, TwoWaySubjectSourceMixin):
    """
    Returns a single SubjectGroup
    """
    queryset = models.SubjectGroup.objects.all()
    serializer_class = serializers.create_sg_serializer('subjectgs', models.SubjectGroup,
                                                        serializers.SubjectSerializer)
    permission_classes = (StandardObjectPermissions,)
    lookup_field = 'id'
    filter_backends = (create_gp_filter_class('subjectgf',
                                              ('observations.view_subjectgroup',),
                                              models.SubjectGroup),)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['render_last_location'] = True
        context['two_way_subject_sources'] = self.two_way_subject_sources

        return context

    def get_queryset(self):
        queryset = models.SubjectGroup.objects.get_non_cyclic_subjectgroups(
            single_sg=True)
        queryset.order_by('name')
        self._get_two_way_sources(queryset)
        return queryset


class SourceGroupsView(generics.ListAPIView):
    """
    Returns all sourcegroups in the system.
    """
    serializer_class = serializers.create_sg_serializer('sourcegs',
                                                        models.SourceGroup,
                                                        serializers.SourceSerializer)
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (create_gp_filter_class('sourcegf',
                                              ('observations.view_sourcegroup',),
                                              models.SourceGroup),)

    def get_queryset(self):
        queryset = models.SourceGroup.objects.filter(_parents=None)
        # Sorting SourceGroups based on name (use '-name' for descending order)
        queryset = queryset.order_by('name')
        return queryset


class SourceGroupView(generics.ListAPIView):
    """
    Return all sources of given source Group (sourcegroup/sources/<name/id>/)
    """
    serializer_class = serializers.SourceSerializer
    lookup_field = 'slug'  # slug can have value of source group's name or id

    def get_queryset(self):
        slug = self.kwargs['slug']
        source_group = models.SourceGroup.objects.filter(name=slug).first()
        if not source_group:
            source_group = models.SourceGroup.objects.filter(id=slug).first()
        if source_group:
            return source_group.get_all_sources()
        return None


class RegionSubjectsView(generics.ListAPIView, TwoWaySubjectSourceMixin):
    lookup_field = 'slug'
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)

    schema = InactiveSubjectsViewSchema()

    def get_queryset(self):
        region = generics.get_object_or_404(models.Region.objects.all(),
                                            slug=self.kwargs.get('slug'))
        queryset = models.Subject.objects.all()
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        subjects = queryset.by_region(region).annotate_with_subjectstatus()

        return subjects

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['two_way_subject_sources'] = self.two_way_subject_sources

        return context


class SubjectsViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [
                {
                    'name': 'tracks_since',
                    'in': 'query',
                    'description': 'Include tracks since this timestamp'
                },
                {
                    'name': 'tracks_until',
                    'in': 'query',
                    'description': 'Include tracks up through this timestamp',
                },
                {
                    'name': 'bbox',
                    'in': 'query',
                    'description': 'Include subjects having track data within this bounding box defined by a 4-tuple of coordinates marking west, south, east, north.',
                },
                {
                    'name': 'subject_group',
                    'in': 'query',
                    'description': 'Indicate a subject group for which Subjects should be listed.'
                },
                {
                    'name': 'subject_group',
                    'in': 'query',
                    'description': 'Indicate a subject group for which Subjects should be listed.',
                    'schema': {'type': 'UUID'}
                },
                {
                    'name': 'name',
                    'in': 'query',
                    'description': 'Find subjects with the given name.',
                    'schema': {'type': 'UUID'}
                },
                {
                    'name': 'updated_since',
                    'in': 'query',
                    'description': 'Return Subject that have been updated since the given timestamp.'
                },
                {
                    'name': 'render_last_location',
                    'in': 'query',
                    'description': 'Indicate whether to render each subject\'s last location.'
                },
                {
                    'name': 'tracks',
                    'in': 'query',
                    'description': 'Indicate whether to render each subject\'s recent tracks.'
                },
                {
                    'name': 'id',
                    'in': 'query',
                    'description': 'A comma-delimited list of Subject IDs.'
                }]

            operation['parameters'].extend(query_params)
        return operation


class SubjectsView(generics.ListCreateAPIView, TwoWaySubjectSourceMixin):
    """
    get:
    Returns a list of Subject in the system.

    """
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    #filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = OptionalResultsSetPagination

    TRACK_QPARAMS = ('tracks_limit',)
    TRACK_DATE_QPARAMS = ('tracks_since', 'tracks_until')

    schema = SubjectsViewSchema()

    # Ensure this attribute is present with a sensible default for any child
    # classes.
    subject_linked_sources = {}

    window_asc = {
        'partition_by': F('subject_id'),
        'order_by': [F('assigned_range').asc(), ],
    }
    window_desc = {
        'partition_by': F('subject_id'),
        'order_by': [F('assigned_range').desc(), ],
    }

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise UnauthorizedView

        use_last_known_location = parse_bool(
            self.request.query_params.get("use_lkl"))

        self.subject_linked_sources = {}

        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        mou_date = self.request.user.additional.get('expiry', None)
        mou_date = dateparse(mou_date) if mou_date else None

        queryset = models.Subject.objects.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24, mou_expiry_date=mou_date
        )
        # need a stable sort for pagination. this needs to match the distinct
        # parameter set in by_user_subjects
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.order_by('id')

        queryset = queryset.by_user_subjects(self.request.user)

        queryset = queryset.select_related(
            'subject_subtype', 'subject_subtype__subject_type', 'common_name'
        )

        # Allow specifying a single subject group by 'id'.
        subject_group = self.request.query_params.get('subject_group')

        # Allow specifying a comma-delimited list of subject IDs.
        subject_ids = self.request.query_params.get('id')

        if subject_ids:
            queryset = queryset.by_id(subject_ids)
        elif subject_group:
            groups = models.SubjectGroup.objects.get_nested_groups(
                subject_group)
            queryset = queryset.by_groups(groups)
        else:
            # Fetch all the Subjects whose access is gained through Source Group
            # permissions.
            source_groups = models.SourceGroup.objects.filter(
                permission_sets__in=self.request.user.get_all_permission_sets())

            subjects_via_source_groups = models.Subject.objects.filter(
                subjectsource__source__groups__in=source_groups)
            subjects_via_source_groups = check_to_include_inactive_subjects(
                self.request, subjects_via_source_groups)
            queryset = queryset.distinct() | subjects_via_source_groups.distinct()

            if not self.request.user.is_superuser:
                # TODO: rather than this, can we get the latest & oldest observation for each subject? (needed in
                #  serializer.to_representation)
                subject_linked_sources = models.SubjectSource.objects.filter(
                    source__groups__in=source_groups
                ).annotate(
                    latest_range=Window(expression=FirstValue(
                        F('assigned_range')), **self.window_desc),
                    latest_source=Window(expression=FirstValue(
                        F('source_id')), **self.window_desc),
                    oldest_range=Window(expression=FirstValue(
                        F('assigned_range')), **self.window_asc),
                    oldest_source=Window(expression=FirstValue(
                        F('source_id')), **self.window_asc)
                ).distinct(
                    'subject_id'
                ).values(
                    'subject_id',
                    'latest_range',
                    'oldest_range',
                    'latest_source',
                    'oldest_source'
                )

                self.subject_linked_sources = {
                    ss['subject_id']: ss for ss in subject_linked_sources
                }

            self._get_two_way_sources(queryset)

        # Apply request query filters that have are compatible with any of the
        # criteria above.
        updated_since = self.request.query_params.get('updated_since')
        updated_until = self.request.query_params.get('updated_until')

        is_updated_since_valid, updated_since = check_valid_date_string(
            updated_since, 'updated_since')
        is_updated_until_valid, updated_until = check_valid_date_string(
            updated_until, 'updated_until')

        if is_updated_since_valid and is_updated_until_valid:
            queryset = queryset.by_updated_since_until(
                updated_since, updated_until)
        elif is_updated_since_valid:
            queryset = queryset.by_updated_since(updated_since)
            updated_until = None
        elif is_updated_until_valid:
            queryset = queryset.by_updated_until(updated_until)
            updated_since = None
        else:
            updated_since = None
            updated_until = None

        bbox = self.request.query_params.get('bbox')

        if bbox:
            bbox = bbox.split(",")
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            if use_last_known_location:
                queryset = queryset.by_bbox_last_known_locations(
                    bbox,
                    last_days=get_track_days(),
                    include_stationary_subjects=include_stationary_subjects_on_map(),
                    updated_since=updated_since,
                    updated_until=updated_until,
                )
            else:
                queryset = queryset.by_bbox(
                    bbox,
                    last_days=get_track_days(),
                    include_stationary_subjects=include_stationary_subjects_on_map(),
                    updated_since=updated_since,
                    updated_until=updated_until,
                )

        if self.request.query_params.get('name', None):
            queryset = queryset.by_name_search(
                self.request.query_params.get('name'))

        return queryset

    def get_serializer_context(self):
        request = self.request
        context = super().get_serializer_context()
        context['render_last_location'] = True
        context['tracks'] = False
        context['subject_linked_sources'] = self.subject_linked_sources
        context['two_way_subject_sources'] = self.two_way_subject_sources

        if request and parse_bool(request.query_params.get('tracks', None)):
            context['tracks'] = True
            for t in self.TRACK_QPARAMS:
                context[t] = request.query_params.get(t, None)
            for t in self.TRACK_DATE_QPARAMS:
                context[t] = dateparse(request.query_params.get(
                    t, None)) if request.query_params.get(t, None) else None
        return context

    def create(self, request, *args, **kwargs):
        many = True if isinstance(request.data, list) else False

        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SubjectsGeoJsonView(SubjectsView):
    serializer_class = serializers.SubjectGeoJsonSerializer
    pagination_class = StandardResultsSetGeoJsonPagination
    renderer_classes = (ExtendedGEOJSONRenderer,)


class SubjectView(generics.RetrieveUpdateDestroyAPIView, TwoWaySubjectSourceMixin):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.SubjectSerializer
    lookup_field = 'id'

    def get_queryset(self):
        subject_id = self.kwargs.get('id')
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise UnauthorizedView
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects.filter(id=subject_id)
        mou_date = self.request.user.additional.get('expiry', None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
        self._get_two_way_sources(queryset)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['two_way_subject_sources'] = self.two_way_subject_sources

        return context


class SubjectSubjectSourcesView(generics.ListAPIView):
    """View for a Subject's SubjectSource records"""
    serializer_class = SubjectSourceSerializer

    def get_queryset(self, *args, **kwargs):
        subject = get_object_or_404(Subject, pk=self.kwargs["id"])
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied
        return SubjectSource.objects.get_subject_sources(subject)


class SubjectSourcesView(generics.ListCreateAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])  # <-- Maybe annotate with subject_status
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied
        subject_sources = models.SubjectSource.objects.get_subject_sources(
            subject)
        sources = models.Source.objects.filter(
            pk__in=subject_sources.values('source'))
        return sources

    def create(self, request, *args, **kwargs):
        request.data["subject"] = self.kwargs["id"]
        serializer = SubjectSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SourceSubjectsView(generics.ListCreateAPIView, TwoWaySubjectSourceMixin):
    serializer_class = serializers.SubjectSerializer

    def get_queryset(self):
        source = generics.get_object_or_404(
            models.Source.objects.all(), pk=self.kwargs['id'])
        # if not self.request.user.has_any_perms(models.Source.VIEW_SUBJECT_PERMS, source):
        #     raise PermissionDenied
        queryset = models.Subject.objects.all()
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        self._get_two_way_sources(queryset)
        return queryset.filter(subjectsource__source=source).annotate_with_subjectstatus()

    def create(self, request, *args, **kwargs):
        request.data["subject"] = self.kwargs["id"]
        serializer = SubjectSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['two_way_subject_sources'] = self.two_way_subject_sources
        return context


class SubjectSourceView(generics.RetrieveAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])  # .annotate_with_subjectstatus()
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        return models.Source.objects.all()

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['source_id']}

        obj = generics.get_object_or_404(queryset, **filters)
        self.check_object_permissions(self.request, obj)
        return obj


class SubjectSourceTrackView(generics.RetrieveAPIView):
    lookup_field = 'id'
    serializer_class = serializers.TrackSerializer
    queryset = models.Subject.objects.all()  # .annotate_with_subjectstatus()
    permission_classes = (StandardObjectPermissions,)
    schema = None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        subject = self.get_object()
        source_id = self.kwargs['source_id']

        since = self.request.query_params.get('since', None)
        if isinstance(since, str):
            since = dateparse(since)

        until = self.request.query_params.get('until', None)
        if until:
            until = dateparse(until)

        sds = models.SubjectSource.objects.get_subject_source(
            subject, source_id)
        if not sds:
            raise Http404

        if since is None:
            since = datetime.datetime.now(tz=pytz.UTC) - get_track_days()

        coordinates = []
        times = []
        for ob in models.Observation.objects.get_subject_source_observation_values(sds, since, until):
            coordinates.append(ob['location'].coords)
            times.append(zeroout_microseconds(ob['recorded_at']))

        context['times'] = times
        context['coordinates'] = coordinates
        return context


class SubjectStatusView(generics.RetrieveAPIView):
    lookup_url_kwarg = 'subject_id'
    lookup_field = 'subject_id'
    serializer_class = serializers.SubjectStatusSerializer

    def get_queryset(self):
        ss = models.SubjectStatus.objects.select_related(
            'subject').filter(delay_hours=0)

        return ss

    def check_object_permissions(self, request, obj):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, obj.subject):
            raise PermissionDenied


class SubjectTracksView(generics.RetrieveAPIView):
    """
    Optional qparam of:
    limit
    since starting date range for the requested track, default follow the tracks logic of returning x number of days. ISO date/time
    until stop date range for the requested track, default is now. ISO date/time
    """
    lookup_url_kwarg = 'subject_id'
    serializer_class = serializers.SubjectTrackSerializer

    def get_queryset(self):
        self.subject_linked_sources = []
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        queryset = models.Subject.objects.all()
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24
        )

        return queryset

    def check_object_permissions(self, request, obj):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, obj):
            source_groups = models.SourceGroup.objects.filter(
                permission_sets__in=request.user.get_all_permission_sets())
            all_allowed_sources = []
            for source_group in source_groups:
                all_allowed_sources.extend(source_group.get_all_sources())

            # Check if Subject's current source
            subject_sources = models.SubjectSource.objects.get_subject_sources(
                obj)
            sources = models.Source.objects.filter(
                pk__in=subject_sources.values('source'))

            pass_flag = False
            for source in sources:
                if source in all_allowed_sources:
                    self.subject_linked_sources.append(source)
                    pass_flag = True

            if not pass_flag:
                raise PermissionDenied

    def get_object(self):
        try:
            return self._cached_object
        except AttributeError:
            pass
        self._cached_object = super().get_object()

        return self._cached_object

    def get_serializer_context(self):
        context = super().get_serializer_context()

        tracks_limits = TrackLimitSerializer(data=self.request.query_params)
        tracks_limits.is_valid(raise_exception=True)
        context['tracks_limit'] = tracks_limits.validated_data['limit']

        since = self.request.query_params.get('since', None)
        until = self.request.query_params.get('until', None)

        linked_sources = getattr(self, 'subject_linked_sources', None)

        context['tracks_since'] = None
        context['tracks_until'] = None

        if since is not None:
            context['tracks_since'] = dateparse(since)

        if until is not None:
            context['tracks_until'] = dateparse(until)

        context['subject_linked_sources'] = linked_sources

        return context


class ObservationView(generics.RetrieveUpdateDestroyAPIView):
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    lookup_field = 'id'
    serializer_class = serializers.ObservationSerializer

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_OBSERVATION_PERMS):
            raise UnauthorizedView

        queryset = models.Observation.objects.all()

        mou_date = self.request.user.additional.get('expiry', None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)
        return queryset


class SourceView(generics.RetrieveUpdateDestroyAPIView, generics.CreateAPIView):
    lookup_fields = ('id', 'manufacturer_id')

    queryset = models.Source.objects.all()
    serializer_class = serializers.SourceSerializer

    def get_object(self):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        filter = {}

        for p in self.lookup_fields:
            pval = self.kwargs.get(p, None)
            if pval is not None:
                filter[p] = pval

        return generics.get_object_or_404(queryset, **filter)


class SourcesView(generics.ListCreateAPIView, ):
    serializer_class = serializers.SourceSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination

    lookup_fields = {'manufacturer_id': 'manufacturer_id__in',
                     'provider_key': 'provider__provider_key__in',
                     'provider': 'provider__provider_key__in',
                     'id': 'id__in'}

    def get_queryset(self):
        queryset = models.Source.objects.all()

        filter = {}
        for fn, fld in self.lookup_fields.items():
            if fn in self.request.query_params:
                filter[fld] = parse_comma(self.request.query_params.get(fn))
        if filter:
            queryset = queryset.filter(**filter)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class SourceProvidersView(generics.ListCreateAPIView, ):
    serializer_class = serializers.SourceProviderSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination

    lookup_field = 'provider_key'

    def get_queryset(self):
        queryset = models.SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class SourceProvidersViewPartial(generics.UpdateAPIView):
    serializer_class = serializers.SourceProviderSerializer
    permission_classes = (StandardObjectPermissions,)
    lookup_field = 'id'

    def get_queryset(self):
        queryset = models.SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class ObservationsViewSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == "GET":
            query_params = [
                {'name': 'subject_id', 'in': 'query',
                    'description': 'filter to a single subject'},
                {'name': 'source_id', 'in': 'query',
                    'description': 'filter to a single source'},
                {'name': 'subjectsource_id', 'in': 'query',
                    'description': 'filter to a subjectsource_id, rather than source_id + time range'},
                {'name': 'since', 'in': 'query',
                    'description': 'get observations after this ISO8061 date, include timezone'},
                {'name': 'until', 'in': 'query',
                    'description': 'get observations up to this ISO8061 date, include timezone'},
                {'name': 'filter', 'in': 'query',
                    'description': 'filter using exclusion_flags for an observation. one of [null, 0, 1, 2  or 3].'},
                {'name': 'include_details', 'in': 'query',
                    'description': ' one of [true,false], default is false. This brings back the observation additional field'},
                {'name': 'created_after', 'in': 'query',
                 'description': 'get observations created (saved in EarthRanger) after this ISO8061 date, include timezone'},
                {'name': 'use_cursor', 'in': 'query',
                 'description': 'default is to use a page based paginator, which does not scale to a large dataset. Set use_cursor=true to employ a paginator that can handle millions of rows by using next/prev urls.'},
            ]
            operation['parameters'].extend(query_params)
        return operation


class ObservationsCursorPagination(StandardResultsSetCursorPagination):
    cursor_query_Param = "id"
    ordering = "recorded_at"


class ObservationsView(generics.ListCreateAPIView):
    serializer_class = serializers.ObservationSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (StandardObjectPermissions,)
    schema = ObservationsViewSchema()

    @property
    def paginator(self):
        """The paginator instance associated with the view, or `None`.
           API caller can request to use a cursor based paginator.

        Returns:
            paginator: the requested paginator
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = ObservationsCursorPagination() if parse_bool(
                    self.request.query_params.get('use_cursor')) else self.pagination_class()
        return self._paginator

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        output = []
        for item in page:
            output.append(
                self.serializer_class.dict_to_representation(
                    item,
                    request.query_params
                )
            )

        return self.get_paginated_response(output)

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_OBSERVATION_PERMS):
            raise UnauthorizedView

        query_params = self.request.query_params
        since = query_params.get('since', None)
        until = query_params.get('until', None)
        recorded_since_is_valid, recorded_since = check_valid_date_string(
            since, 'recorded_since')
        recorded_until_is_valid, recorded_until = check_valid_date_string(
            until, 'recorded_until')
        subject_id = query_params.get('subject_id', None)
        source_id = query_params.get('source_id', None)
        subjectsource_id = query_params.get('subjectsource_id', None)
        created_after = query_params.get('created_after', None)
        filter_flag = 0
        filter_qparam = query_params.get('filter', 0)
        try:
            filter_flag = int(filter_qparam)
        except (ValueError, TypeError):
            filter_flag = None if filter_qparam == 'null' else filter_flag

        if len([id for id in (subject_id, source_id, subjectsource_id) if id]) > 1:
            raise ValueError(
                "Can only specify one of: subject_id and source_id and subjectsource_id")
        elif subject_id:
            subject = get_object_or_404(models.Subject, pk=subject_id)
            if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
                raise PermissionDenied

            queryset = models.Observation.objects.get_subject_observations(
                subject, since=recorded_since, until=recorded_until, filter_flag=filter_flag, order_by='recorded_at')
        elif source_id:
            queryset = models.Observation.objects.get_source_observations(
                source_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag, order_by='recorded_at')
        elif subjectsource_id:
            queryset = models.Observation.objects.get_subjectsource_observations(
                subjectsource_id, since=recorded_since, until=recorded_until, filter_flag=filter_flag, order_by='recorded_at')
        else:
            queryset = models.Observation.objects.by_since_until(
                recorded_since, recorded_until)
            queryset = queryset.by_exclusion_flags(filter_flag)
            queryset = queryset.order_by('recorded_at')

        mou_date = self.request.user.additional.get('expiry', None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None
        created_after = dateparse(created_after) if created_after else None

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)

        if created_after:
            queryset = queryset.by_created_after(created_after)

        queryset = queryset.annotate_transforms()
        queryset = queryset.prefetch_related('source__provider__transforms')

        return queryset.values()

    def create(self, request, *args, **kwargs):
        '''
         On condition of post body being a list, let it bulk insert.
        :param request:
        :param args:
        :param kwargs:
        :return:
        '''
        serializer = serializers.ObservationSerializer(
            many=isinstance(request.data, list), data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST, )
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_serializer_context(self):
        context = super(ObservationsView, self).get_serializer_context()

        # Check request before accessing params since self.request is None when
        # generating docs schema
        context['include_details'] = parse_bool(self.request.query_params.get(
            'include_details', False)) if self.request else False

        return context

    def get_serializer_class(self):
        if self.request.query_params.get('json_format', None) == 'flat':
            return serializers.FlattenObservationSerializer
        return super(ObservationsView, self).get_serializer_class()


class KmlRootView(generics.GenericAPIView):
    renderer_classes = (StaticHTMLRenderer,)

    def build_link_for_user(self, start_date=None, end_date=None):
        token = kmlutils.get_kml_access_token(self.request.user, )
        include_active = self.request.GET.get('include_inactive')
        include_active = parse_bool(include_active)
        params = {k: v for k, v in
                  zip(['auth', 'start', 'end', 'include_inactive'],
                      [token, start_date, end_date, include_active]) if v}
        params = urllib.parse.urlencode(params)
        url = reverse('subjects-kml-view')
        return utils.add_base_url(self.request, f"{url}?{params}")

    def get(self, request, *args, **kwargs):
        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')
        start = None
        end = None

        if start_date:
            try:
                start_date = dateutil.parser.parse(start_date)
                start = start_date.isoformat()
            except Exception as e:
                return Response(data={"start": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = dateutil.parser.parse(end_date)
                end = end_date.isoformat()
            except Exception as e:
                return Response(data={"end": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Have a configuration for naming the KML feed.
        filename = 'DAS-KML_{}_{}'.format(self.request.user.username,
                                          datetime.datetime.now(tz=pytz.utc).strftime('%Y%M%d%H%M'))

        context = {'network_link':
                   {'name': settings.KML_FEED_TITLE,
                    'visibility': 0,
                    'open': 1,
                    'href': self.build_link_for_user(start, end)
                    }
                   }

        result = render_to_string('kml/user_root.xml', context)

        return kmlutils.render_to_kmz(result, filename)


class KmlSubjectsView(generics.GenericAPIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer,)

    def get_queryset(self):
        include_inactive = self.request.GET.get('include_inactive', 'false')

        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')

        # verify date in YYYY-mm-dd
        try:
            dateutil.parser.parse(start_date)
        except Exception:
            start_date = None

        try:
            dateutil.parser.parse(start_date)
        except Exception:
            end_date = None

        if start_date or end_date:
            queryset = get_subjects_with_observations_in_daterange(
                start_date, end_date)
        else:
            # return all subjects with or without tracks if no date
            # filter is passed
            queryset = models.Subject.objects.all()
        queryset = queryset.by_user_subjects(self.request.user)
        if not parse_bool(include_inactive):
            queryset = queryset.filter(is_active=True)
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        return queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24)

    def build_link_for_subject(self, subject):
        token = kmlutils.get_kml_access_token(self.request.user)
        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')
        params = {k: v for k, v in
                  zip(['auth', 'start', 'end'],
                      [token, start_date, end_date]) if v}
        params = urllib.parse.urlencode(params)
        url = reverse('subject-kml-view', args=[subject['id']])
        return utils.add_base_url(self.request, f"{url}?{params}")

    def subject_context(self, subject):

        return {'name': subject.name,
                'visibility': 0,
                'href': self.build_link_for_subject(subject)
                }

    @staticmethod
    def get_display_subtype(subtype):
        '''
        Get the human name or subtype.
        :param subtype:
        :return:
        '''
        try:
            return models.SubjectSubType.objects.get(value=subtype).display
        except Exception as e:
            logger.exception(e)
            return 'Unassigned'

    def get(self, request, *args, **kwargs):

        subjects = list(self.get_queryset().values(
            'additional', 'name', 'id', 'subject_subtype'))

        DEFAULT_REGION_NAME = 'Unknown Region'

        subject_list = [{'name': subject['name'],
                         'species': self.get_display_subtype(subject.get('subject_subtype')),
                         'region': subject.get('additional').get('region') if isinstance(subject.get('additional').get('region'), str) else DEFAULT_REGION_NAME,
                         'visibility': 0,
                         'href': self.build_link_for_subject(subject)
                         } for subject in subjects
                        ]
        #
        context = {'title': 'DAS Tracking Data',
                   'visibility': 1,
                   'subject_list': subject_list
                   }

        filename = 'DAS-KML-Subjects_{}_{}'.format(self.request.user.username,
                                                   datetime.datetime.now(tz=pytz.utc).strftime('%Y%M%d%H%M'))

        result = render_to_string('kml/subject_list.xml', context)
        return kmlutils.render_to_kmz(result, filename)


def rgb_to_hex(red, green, blue):
    """Return color as #rrggbb for the given color values."""
    return 'ff%02x%02x%02x' % (int(red), int(green), int(blue))


class KmlSubjectView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer,)
    lookup_field = 'id'

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs.get('id'))
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS,
                                               subject):
            raise PermissionDenied

        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects.all().annotate_with_subjectstatus(
            delay_hours=min_age_days * 24)
        return queryset

    def get_subject_color(self, subject):
        '''
        Be careful reusing this function. Take note of the unusual order of hues in the result.
        :param subject:
        :return:
        '''
        try:
            red, green, blue = subject.additional['rgb'].split(',')
            kml_color = 'ff%02x%02x%02x' % (int(blue), int(green), int(red))
        except:
            kml_color = 'ff000000'  # Default is black.

        return kml_color

    def get_allowed_subject_observations(self, subject, filter_parameters=None):
        start_timestamp = filter_parameters.get('start')
        end_timestamp = filter_parameters.get('end')
        filter_flag = filter_parameters.get('filter', 0)

        maximum_history_days = 60
        if start_timestamp:
            delta = datetime.datetime.now(pytz.utc) - start_timestamp
            if delta.days > maximum_history_days:
                maximum_history_days = delta.days
        (lower, upper) = calculate_subject_view_window(
            self.request.user, maximum_history_days)

        if lower >= upper:
            raise PermissionDenied

        if start_timestamp and upper >= start_timestamp >= lower:
            lower = start_timestamp
        if end_timestamp and upper >= end_timestamp >= lower:
            upper = end_timestamp
        if start_timestamp and end_timestamp \
                and end_timestamp < start_timestamp:
            raise ValueError('Start date can not be greater than end date.')

        return models.Observation.objects.get_subject_observations_values(
            subject, since=lower, until=upper, filter_flag=filter_flag
        )

    def parse_filter_parameters(self):
        """
       Parse GET request filter parameters.
       :return: Dict of filter parameters in the appropriate format.
       """
        filter_parameters = {}
        try:
            if self.request.GET.get('start'):
                filter_parameters.update({
                    'start': dateutil.parser.parse(
                        self.request.GET.get('start'))})
        except (ValueError, TypeError):
            raise ValueError('Invalid start-date format - {}'.format(
                self.request.GET.get('start')))
        try:
            if self.request.GET.get('end'):
                filter_parameters.update({
                    'end': dateutil.parser.parse(
                        self.request.GET.get('end'))})
        except (ValueError, TypeError):
            raise ValueError('Invalid end-date format - {}'.format(
                self.request.GET.get('end')))
        try:
            if self.request.GET.get('filter'):
                filter_parameters.update({
                    'filter': int(self.request.GET.get('filter', 0))})
        except (ValueError, TypeError):
            raise ValueError('Invalid filter flag format - {}'.format(
                self.request.GET.get('filter')))
        return filter_parameters

    def get(self, request, *args, **kwargs):

        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        subject = generics.get_object_or_404(
            models.Subject.objects.all().annotate_with_subjectstatus(
                delay_hours=min_age_days * 24),
            pk=self.kwargs['id'])
        filter_parameters = self.parse_filter_parameters()
        self.check_object_permissions(self.request, subject)

        observations = list(self.get_allowed_subject_observations(
            subject, filter_parameters))

        filename = 'DAS-KML_{}-{}'.format(re.sub('[^a-zA-Z0-9]', '_', subject.name),
                                          datetime.datetime.now(tz=pytz.utc).strftime('%Y%M%d%H%M'))

        kml_overlay_image = getattr(settings, 'KML_OVERLAY_IMAGE', None)

        color = self.get_subject_color(subject)
        context = {
            'name': subject.name,
            'observations': observations,
            'points_color': color,
            'track_color': color,
            'last_position_color': color,
            'subject_icon': utils.add_base_url(request, subject.kml_image_url),
            'kml_overlay_image': utils.add_base_url(request, kml_overlay_image) if kml_overlay_image else None,
            'timezone_name': current_tz_name,
            'timezone': current_tz
        }
        result = render_to_string('kml/subject_track.xml', context)
        return kmlutils.render_to_kmz(result, filename)


class TrackingDataViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [
                {
                    'name': 'current_status',
                    'in': 'query',
                    'description': 'Get current status or historical observations',
                    'schema': {'type': 'bool'}
                },
                {
                    'name': 'subject_id',
                    'in': 'query',
                    'description': 'Get data for specific subject ID',
                    # 'schema': {'type': 'integer'}
                },
                {
                    'name': 'subject_chronofile',
                    'in': 'query',
                    'description': 'Get data for specific chronofiles',
                    'schema': {'type': 'integer'}
                },
                {
                    'name': 'filter',
                    'in': 'query',
                    'description': 'Add Exclusion flags as a bitmap. oneof [null, 0, 1, 2, 3]',
                    # 'schema': {'type': 'integer'}
                },
                {
                    'name': 'format',
                    'in': 'query',
                    'description': 'Return report as CSV or JSON',
                    'schema': {'type': 'string'}
                },
                {
                    'name': 'before_date',
                    'in': 'query',
                    'description': 'Return report before given date',
                    # 'schema': {'type': 'string'}
                },
                {
                    'name': 'after_date',
                    'in': 'query',
                    'description': 'Return report after given date',
                    # 'schema': {'type': 'string'}
                },
                {
                    'name': 'record_serial_base',
                    'in': 'query',
                    'description': 'Return report in order of generated serial number',
                    # 'schema': {'type': 'bool'}
                },
                {
                    'name': 'max_records',
                    'in': 'query',
                    'description': 'Maximum number of records to return',
                    'schema': {'type': 'integer'}
                },
            ]

            operation['parameters'].extend(query_params)
        return operation


class TrackingDataCsvView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)
    schema = TrackingDataViewSchema()

    def get_queryset(self, subject_id=None, chronofile=None):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise PermissionDenied
        queryset = models.Subject.objects.all()
        # To include inactive subjects in trackingdata report
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.by_user_subjects(self.request.user)
        if subject_id:
            queryset = queryset.filter(id=subject_id)
        elif chronofile:
            queryset = queryset.filter(
                subjectsource__additional__chronofile=int(chronofile))

            queryset = queryset.annotate(subjectsource_additional=F('subjectsource__additional'))\
                .annotate(source_model_name=F('subjectsource__source__model_name'))\
                .annotate(source_manufacturer_id=F('subjectsource__source__manufacturer_id'))\
                .annotate(subjectsource_assigned_range=F('subjectsource__assigned_range'))\
                .annotate(source_additional=F('subjectsource__source__additional'))\
                .annotate(source_id=F('subjectsource__source__id'))\
                .annotate(subjectsource_id=F('subjectsource__id'))
        return queryset

    def get(self, request, *args, **kwargs):
        # Set exclusion flag value
        filter_flag = 0
        qparam = self.request.GET.get('filter', 0)
        try:
            filter_flag = int(qparam)
        except (ValueError, TypeError):
            filter_flag = None if qparam == 'null' else filter_flag

        try:
            request_date_after = parse_datetime(
                self.request.GET.get('after_date', None))
        except:
            request_date_after = None

        try:
            request_date_before = parse_datetime(
                self.request.GET.get('before_date', None))
        except:
            request_date_before = None

        # return in json format or csv, default is csv
        result_format = self.request.GET.get('format', 'csv').lower()

        # get data for a specific subject This is for STE downloader
        request_subject_id = self.request.GET.get(
            'subject_id', None)

        # get data for a specific chronofile? This is for STE downloader
        request_subject_chronofile = self.request.GET.get(
            'subject_chronofile', None)

        # get current status? or historical observations
        get_current = utils.json.parse_bool(self.request.GET.get(
            'current_status', 'false'))

        # This call will embed a in order manufactured serial number per returned row
        #  do we start at 0 or some other number? This is for STE downloader
        record_serial_base = int(
            self.request.GET.get('record_serial_base', -1))

        # max number of records to return
        max_records = int(self.request.GET.get('max_records', -1))

        # Time range to query observation data according to user's permission
        max_days = 36500  # View All time days permission's number of days
        (lower, upper) = calculate_subject_view_window(
            self.request.user, max_days)
        if lower >= upper:
            raise PermissionDenied

        # if passed in bounds further restrict calculated ones for the user,
        # use those
        upper = request_date_before if request_date_before is not None and request_date_before < upper else upper
        lower = request_date_after if request_date_after is not None and request_date_after > lower else lower

        # Get SubjectSource and Observations with in time range for subjects
        fixtime_label = 'fixtime ({})'.format(
            tz_offset) if result_format == 'csv' else 'fixtime'
        dloadtime_label = 'dloadtime ({})'.format(
            tz_offset) if result_format == 'csv' else 'dloadtime'
        fieldnames = ['chronofile', 'recordserial', 'observation_id', 'collar_id', fixtime_label, dloadtime_label,
                      'lon', 'lat', 'height', 'temp', 'voltage']
        csv_data = []
        cur_record_serial = record_serial_base
        if get_current:
            # all the current status objects for the allowed subjects
            items = self.get_subject_status_queryset(
                max_records, request_subject_id, request_subject_chronofile)
            if items:
                for item in items:
                    cur_record_serial += 1
                    data = self.get_csv_observation_data(cur_record_serial, dloadtime_label, fixtime_label, result_format,
                                                         item, item['subject_id'] if request_subject_id else None, None)
                    csv_data.append(data)
        else:
            try:
                subjects = self.get_queryset(
                    request_subject_id, request_subject_chronofile)
                for subject in subjects:
                    # all the relevant observations for the subject
                    for item in self.get_subject_trackdata_queryset(
                            filter_flag, lower, subject, upper, max_records).values():
                        cur_record_serial += 1
                        data = self.get_csv_observation_data(cur_record_serial, dloadtime_label, fixtime_label, result_format,
                                                             item, subject.id if request_subject_id else None, None)
                        csv_data.append(data)
            except django.core.exceptions.ValidationError:
                raise ValidationError(
                    {'Error': f'{request_subject_id} is not a valid UUID'})

        timestamp = current_tz.localize(datetime.datetime.utcnow())

        if result_format != 'csv':
            return Response(csv_data)

        download_filename = f'Tracking Data {timestamp.strftime("%Y-%m-%d")}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment;filename={download_filename}'
        response['x-das-download-filename'] = download_filename

        if request_subject_id:
            fieldnames = [item.replace('chronofile', 'subject_id')
                          for item in fieldnames]
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        if csv_data:
            writer.writerows(csv_data)
        return response

    def get_csv_observation_data(self, cur_record_serial, dloadtime_label, fixtime_label, result_format, item,
                                 subject_id, subject_chronofile):
        recorded_at = item['recorded_at'].astimezone(
            current_tz) if result_format == 'csv' else item['recorded_at']
        created_at = item['created_at'].astimezone(
            current_tz) if result_format == 'csv' else item['created_at']

        request_key = 'chronofile'
        if subject_id:
            request_key, value = 'subject_id', subject_id
        elif subject_chronofile:
            value = subject_chronofile
        else:
            value = item['subjectsource_additional'].get('chronofile', '') \
                if item['subjectsource_additional'] else ''

        collar_id = item['collar_id']
        data = {'observation_id': item['id'],
                'lat': item['location'].y,
                'lon': item['location'].x,
                'height': item['location'].z,
                request_key: value,
                'collar_id': collar_id,
                'recordserial': cur_record_serial,
                fixtime_label: recorded_at.strftime('%m/%d/%Y %H:%M:%S') if result_format == 'csv'
                else recorded_at.isoformat(),
                dloadtime_label: created_at.strftime('%m/%d/%Y %H:%M:%S') if result_format == 'csv'
                else created_at.isoformat(),
                'temp': self.get_temperature(item),
                'voltage': self.get_voltage(item),
                }
        return data

    @staticmethod
    def get_temperature(item):
        additional = item.get('additional')
        if additional:
            return additional.get('temp') or additional.get('temperature', 0)
        return 0

    @staticmethod
    def get_voltage(item):
        additional = item.get('additional')
        if additional:
            return additional.get('voltage') or additional.get('battery') or additional.get('batt', 0)
        return 0

    def get_subject_trackdata_queryset(self, filter_flag, lower, subject, upper, max_records):
        if hasattr(subject, "subjectsource_id"):
            qs = models.Observation.objects.get_subjectsource_observations(
                subject.subjectsource_id, lower, upper, max_records, filter_flag=filter_flag, order_by='recorded_at')
        else:
            qs = models.Observation.objects.get_subject_observations(
                subject, lower, upper, max_records, filter_flag=filter_flag, order_by='recorded_at')
        qs = qs.annotate(subjectsource_additional=F('source__subjectsource__additional'),
                         collar_id=F('source__manufacturer_id'))
        return qs

    def get_subject_status_queryset(self, max_records, subject_id=None, chronofile=None):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        qs = models.SubjectStatus.objects.filter(delay_hours=min_age_days * 24)\
            .filter(subject__subjectsource__assigned_range__contains=now)
        if subject_id:
            qs = qs.filter(subject__id=subject_id)
        elif chronofile:
            qs = qs.filter(
                subject__subjectsource__additional__chronofile=int(chronofile))
        else:
            qs = qs.filter(
                subject__subjectsource__additional__chronofile__isnull=False)

        qs = qs.annotate(subjectsource_additional=F('subject__subjectsource__additional'),
                         collar_id=F('subject__subjectsource__source__manufacturer_id')).values()
        if max_records > 0:
            qs = qs[:max_records]
        return qs.values()


class TrackingMetaDataExportView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)
    # schema = InactiveSubjectsViewSchema()

    def get_source_details(self, format):
        """
        Gather required details for each Subject/Source combination.
        :return: List of dictionaries containing required details.
        """
        tracking_metadata = []
        data_starts = 'data_starts ({})'.format(
            tz_offset) if format != 'json' else 'data_starts'
        data_stops = 'data_stops ({})'.format(
            tz_offset) if format != 'json' else 'data_stops'
        headers = ['chronofile', 'collar_type', 'collar_id', 'active',
                   'datasource', 'frequency', 'animal_id', 'name', 'species',
                   'subtype', 'groups', data_starts, data_stops,
                   'date_off_or_removed', 'comments',
                   'predicted_expiry', 'rgb', 'sex', 'gmt', 'data_status',
                   'data_starts_source', 'data_stops_source',
                   'data_stops_reason', 'collar_status', 'collar_model',
                   'has_acc_data', 'data_owners', 'region', 'country', 'subject_id', 'source_id', 'subjectsource_id']

        # NOTE: nearly all the data for this call is actually found in the source and subject source, however
        #       it is the subject and by association the subject_group that are limited by the user
        #       so make sure to get the source the is currently assigned
        subjects = self.get_queryset()
        subjects = subjects.prefetch_related('subjectsources')\
            .annotate(subjectsource_additional=F('subjectsource__additional'))\
            .annotate(source_model_name=F('subjectsource__source__model_name'))\
            .annotate(source_manufacturer_id=F('subjectsource__source__manufacturer_id'))\
            .annotate(subjectsource_assigned_range=F('subjectsource__assigned_range'))\
            .annotate(source_additional=F('subjectsource__source__additional'))\
            .annotate(source_id=F('subjectsource__source__id'))\
            .annotate(subjectsource_id=F('subjectsource__id'))

        subjectsources = set()
        for subject in subjects:
            if subject.subjectsource_id in subjectsources:
                continue
            subjectsources.add(subject.subjectsource_id)
            subject.subjectsource_additional = {} if subject.subjectsource_additional is None \
                else subject.subjectsource_additional

            source_details = {}
            try:
                # Collect Subject details.
                subject_groups = ','.join(
                    [grp.name for grp in models.SubjectGroup.objects.filter(subjects=subject)])

                source_details.update({
                    'name': subject.name,
                    'species': subject.additional.get('species', ''),
                    'rgb': subject.additional.get('rgb', ''),
                    'sex': subject.additional.get('sex', ''),
                    'region': subject.additional.get('region', ''),
                    'active': subject.is_active,
                    'country': subject.additional.get('country', ''),
                    'subtype': subject.subject_subtype.display,
                    'groups': subject_groups,
                    'subject_id': subject.id,
                    'animal_id': subject.additional.get('tm_animal_id', ''),
                })

                if subject.source_additional is not None:
                    # Collect Source details.

                    lower = subject.subjectsource_assigned_range.lower
                    upper = subject.subjectsource_assigned_range.upper
                    try:
                        if format != 'json':
                            lower = lower.astimezone(current_tz) if lower != datetime.datetime(
                                datetime.MINYEAR, 1, 1, tzinfo=pytz.utc) else lower
                            upper = upper.astimezone(current_tz) if upper != datetime.datetime(
                                datetime.MAXYEAR, 12, 31, tzinfo=pytz.utc)else upper
                    except:
                        pass
                    source_details.update({
                        'chronofile': subject.subjectsource_additional.get(
                            'chronofile', None),
                        'collar_type': subject.source_model_name,
                        'collar_id': subject.source_manufacturer_id,
                        'datasource': subject.source_additional.get(
                            'datasource', ''),
                        'frequency': subject.source_additional.get(
                            'frequency', 0.0),

                        data_starts: lower.strftime('%m/%d/%Y %H:%M:%S') if format != 'json' else lower.isoformat(),
                        data_stops: upper.strftime('%m/%d/%Y %H:%M:%S') if format != 'json' else upper.isoformat(),
                        'comments': subject.subjectsource_additional.get(
                            'comments', ''),
                        'predicted_expiry':
                            subject.source_additional.get(
                                'predicted_expiry', ''),
                        'data_status': subject.subjectsource_additional.get(
                            'data_status', ''),
                        'data_starts_source':
                            subject.subjectsource_additional.get(
                                'data_starts_source', ''),
                        'data_stops_source':
                            subject.subjectsource_additional.get(
                                'data_stops_source', ''),
                        'data_stops_reason':
                            subject.subjectsource_additional.get(
                                'data_stops_reason', ''),
                        'date_off_or_removed':
                            subject.subjectsource_additional.get(
                                'date_off_or_removed', ''),
                        'collar_status':
                            subject.source_additional.get('collar_status', ''),
                        'collar_model': subject.source_additional.get(
                            'collar_model', ''),
                        'has_acc_data': subject.source_additional.get(
                            'has_acc_data', ''),
                        'data_owners': subject.source_additional.get(
                            'data_owners', ''),
                        'source_id': subject.source_id,
                        'subjectsource_id': subject.subjectsource_id
                    })
            except Exception as error:
                logger.exception(error)
            finally:
                tracking_metadata.append(source_details)
        return tracking_metadata, headers

    def get(self, request, *args, **kwargs):
        # Create the HttpResponse object with the appropriate CSV header.
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.datetime.utcnow())
        format = self.request.GET.get('format', '').lower()
        tracking_metadata, headers = self.get_source_details(format)

        if format == 'json':
            return HttpResponse(
                json.dumps({'metadata': tracking_metadata},
                           cls=DjangoJSONEncoder),
                content_type='application/json', status=status.HTTP_200_OK
            )

        download_filename = f'Tracking Meta Data Export {timestamp.strftime("%Y-%m-%d")}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={download_filename}'
        response['x-das-download-filename'] = download_filename

        writer = csv.DictWriter(response, headers)
        writer.writeheader()
        writer.writerows(tracking_metadata)
        return response

    def get_queryset(self):
        # Get user accessible active subjects.
        queryset = models.Subject.objects.all()
        # To include inactive subjects in trackingmetadata report
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.by_user_subjects_not_distinct(self.request.user)
        return queryset


class GPXFileUploadView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.GPXTrackFileUploadSerializer

    def create(self, request, *args, **kwargs):
        if not self.request.user.has_perm('observations.add_observation'):
            raise PermissionDenied
        source_id = kwargs.get('id')
        get_object_or_404(models.Source, id=source_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)

        inmemory_file = validated_data.get('gpx_file')
        filename = self.save_in_defaultstorage(inmemory_file)
        async_result = self.get_async_result(filename, source_id)
        data = self.create_data(request, inmemory_file,
                                source_id, async_result)
        return Response(data, status=status.HTTP_201_CREATED)

    @staticmethod
    def save_in_defaultstorage(inmemory_file):
        file_path = f'{models.GPX_FILES_FOLDER}/{inmemory_file.name}'
        return default_storage.save(file_path, inmemory_file)

    @staticmethod
    def get_async_result(file, source_id):
        try:
            async_result = process_gpxdata_api.apply_async(
                args=(file, source_id))
        except exceptions.OperationalError as exc:
            raise ValidationError({'error_message': exc})
        else:
            return async_result

    @staticmethod
    def create_data(request, file, source_id, async_result):
        status_url = add_base_url(request, reverse(
            'gpx-status', kwargs={'id': source_id, 'task_id': async_result.id}))
        data = dict(source_id=source_id,
                    filename=file.name,
                    filesize_bytes=file.size,
                    process_status=dict(task_info=async_result.info,
                                        task_id=async_result.id,
                                        task_success=async_result.successful(),
                                        task_failed=async_result.failed(),
                                        task_url=status_url))
        return data


class GPXTaskStatusView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        # status: Pending means task is waiting for execution or unknown.
        # Any task id that is unknown is implied to be in pending state.
        task_id = self.kwargs.get('task_id')
        asyncResult = celery.app.AsyncResult(task_id)
        result = dict(error_msg=asyncResult.result.message) \
            if isinstance(asyncResult.result, Exception) else asyncResult.result

        data = dict(task_result=result,
                    task_status=asyncResult.status.title(),
                    task_success=asyncResult.successful(),
                    task_failed=asyncResult.failed()
                    )
        if asyncResult.status != 'STARTED':
            # Release the resources whenever AsyncResult instance is called.
            asyncResult.forget()
        return Response(data, status=status.HTTP_200_OK)


class MessagesSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [{
                'name': 'subject_id',
                'in': 'query',
                'description': 'Get messages of this subject.'},
                {
                    'name': 'source_id',
                    'in': 'query',
                    'description': 'Get messages of this device/source'},
                {
                    'name': 'read',
                    'in': 'query',
                    'description': 'Get read/unread messages'},
                {
                    'name': 'recent_message',
                    'in': 'query',
                    'description': 'Number of recent messages'},
            ]
            operation['parameters'].extend(query_params)

        elif method == 'POST':
            query_params = [{
                'name': 'subject_id',
                'in': 'query',
                'description': 'Post messages to this subject.'},
                {
                'name': 'source_id',
                'in': 'query',
                'description': 'Post Messages to this device/source'},
                {
                'name': 'manufacturer_id',
                'in': 'query',
                'description': 'Post Messages from a device of this manufacturer id.'}
            ]
            operation['parameters'].extend(query_params)

        return operation


class MessagesView(generics.ListCreateAPIView):
    serializer_class = serializers.MessageSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination
    schema = MessagesSchema()

    def get_queryset(self):
        query_params = self.request.query_params
        messages = get_user_messages(self.request.user)

        subject_id = query_params.get('subject_id')
        source_id = query_params.get('source_id')
        read = query_params.get('read')
        # define with this query-param number of recent_message.
        number_recent_msg = query_params.get('recent_message')
        if subject_id:
            # Accepting a list i.e : ?subject_id=id1, id2, id2
            subject_ids = [x.strip(' ') for x in subject_id.split(',')]
            messages = messages.by_subject_ids(subject_ids)
        if source_id:
            messages = messages.by_source_id(source_id)
        if read is not None:
            messages = messages.by_read(parse_bool(read))

        if number_recent_msg and number_recent_msg.isdigit():
            sender = {'partition_by': F('sender_id'), 'order_by': [
                F('message_time').desc()]}
            receiver = {'partition_by': F('receiver_id'), 'order_by': [
                F('message_time').desc()]}

            messages = messages.annotate(rn_sender=Window(expression=RowNumber(), **sender),
                                         rn_receiver=Window(expression=RowNumber(), **receiver))
            sql, params = messages.query.sql_with_params()
            messages = models.Message.objects.raw("""
            select * from ({}) msgs where  rn_sender<= %s or rn_receiver <= %s """.format(sql),
                                                  params=[*params, number_recent_msg, number_recent_msg])
        return messages

    def post(self, request, *args, **kwargs):
        data = request.data
        if data.get("bulk_read"):
            # Handle bulk reading of messages
            ids, read = data.get("ids"), data.get("read", True)
            ids = [ids] if isinstance(ids, str) else ids

            user_messages = get_user_messages(self.request.user)
            user_msg_ids = [str(k.id) for k in user_messages]
            valid_update_ids = [k for k in ids if k in user_msg_ids]

            msgs = user_messages.filter(id__in=valid_update_ids)
            for m in msgs:
                m.read = read
                m.save()

            read_state = 'read' if read else 'unread'
            return Response(f"{len(valid_update_ids)} messages successfully updated to {read_state}", status=status.HTTP_200_OK)

        return self.create(request, *args, **kwargs)

    def save_message(self, request, data):
        serializer = self.serializer_class(
            data=data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST, )

        serializer.save()
        return serializer.data

    def create(self, request, *args, **kwargs):

        data = request.data
        message_type = data.get("message_type", "outbox")
        data['message_time'] = data.get(
            "message_time", datetime.datetime.now(tz=pytz.utc).isoformat())

        qparams = self.request.query_params
        if message_type == "inbox":
            # Handle Inbox messages

            manufacturer_id = qparams.get("manufacturer_id")
            if not manufacturer_id:
                return Response({"Error": "Manufacturer Id param has to be provided for an inbox message"},
                                status=status.HTTP_400_BAD_REQUEST)

            dt = parse_datetime(data['message_time'])
            for subject_source in models.SubjectSource.objects.filter(source__manufacturer_id=manufacturer_id,
                                                                      assigned_range__contains=dt).distinct('subject'):
                data['sender'] = {
                    "content_type": "observations.subject", "id": subject_source.subject.id}
                data['device'] = str(subject_source.source.id)
                # update incoming message status to received.
                data['status'] = models.RECEIVED
                ser_data = self.save_message(request, data)
        else:
            # Handle Outbox messages

            subject_id = qparams.get('subject_id')
            source_id = qparams.get('source_id')

            if not subject_id and not source_id:
                return Response({"Error": "Source_id and subject_id params needed for an outbox message"},
                                status=status.HTTP_400_BAD_REQUEST)

            # Set logged in user as the sender
            data['sender'] = {
                "content_type": "accounts.user", "id": request.user.id}
            data['receiver'] = {
                "content_type": "observations.subject", "id": subject_id}
            data['device'] = source_id

            ser_data = self.save_message(request, data)

            message_id, user_email = ser_data.get('id'), request.user.email
            handle_outbox_message.apply_async(
                args=(message_id, user_email))

        headers = self.get_success_headers(ser_data)
        return Response(ser_data, status=status.HTTP_201_CREATED, headers=headers)


class MessageView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = 'id'
    serializer_class = serializers.MessageSerializer
    permission_classes = (IsAuthenticated,)
    queryset = models.Message.objects.all()

    def get_queryset(self):
        return get_user_messages(self.request.user)


def get_user_messages(user):
    # Get messages a user has access to
    user_subjects = models.Subject.objects.by_user_subjects(user)
    user_subject_ids = [subj.id for subj in user_subjects]
    messages = models.Message.objects.filter(
        Q(sender_id__in=user_subject_ids) | Q(receiver_id__in=user_subject_ids))
    return messages


class AnnouncementsView(generics.ListCreateAPIView):
    serializer_class = serializers.AnnouncementSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = models.Announcement.objects.all().order_by_announcement_at()

        query_params = self.request.query_params
        is_read = query_params.get('is_read')
        user = self.request.user

        if is_read is not None:
            queryset = queryset.by_read(parse_bool(is_read), user)

        return queryset

    def post(self, request, *args, **kwargs):
        query_params = self.request.query_params
        read = query_params.get('read')
        if not read:
            raise ParseError(
                detail=" Malformed request. Query parameter 'read' is required.")

        data = dict(news_ids=[x.strip() for x in read.split(',')])
        serializer = serializers.ReadAnnouncementSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        queryset = models.Announcement.objects.filter(
            pk__in=serializer.data.get('news_ids'))
        [q.related_users.add(request.user) for q in queryset]

        context = dict(request=self.request)
        response = self.serializer_class(queryset, many=True, context=context)
        return Response(response.data, status=status.HTTP_200_OK)


class SubjectSourceAssignmentSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [{
                'name': 'subjects',
                'in': 'query',
                'description': 'A comma-delimited list of Subject IDs.'},
                {
                    'name': 'sources',
                    'in': 'query',
                    'description': 'A comma-delimited list of Source IDs.'},
            ]
            operation['parameters'].extend(query_params)

        return operation


class SubjectSourcesAssignmentView(generics.ListAPIView):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.SubjectSourceSerializer
    pagination_class = StandardResultsSetPagination
    schema = SubjectSourceAssignmentSchema()

    def get_queryset(self):
        query_params = self.request.query_params

        subjects_list = parse_comma(query_params.get('subjects'))
        sources_list = parse_comma(query_params.get('sources')) or []

        allowed = models.Subject.objects.by_user_subjects(
            self.request.user).values_list('id', flat=True)

        # First get subject-sources user has access to.
        queryset = models.SubjectSource.objects.filter(subject_id__in=allowed)

        if subjects_list and sources_list:
            queryset = queryset.filter(Q(subject_id__in=set(allowed) & set(
                subjects_list)) | Q(source_id__in=sources_list))
        elif subjects_list:
            queryset = queryset.filter(
                subject_id__in=set(allowed) & set(subjects_list))
        elif sources_list:
            queryset = queryset.filter(source_id__in=sources_list)
        return queryset
