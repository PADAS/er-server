import logging
import datetime
import dateutil.parser
import pytz
from io import BytesIO
import re
import json
import csv

from django.conf import settings
from django.urls import reverse
from django.core.serializers.json import DjangoJSONEncoder

from django.utils.dateparse import parse_datetime
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.db.models import Prefetch, F, Q, FilteredRelation, Value
from django.db.models.functions import Coalesce
import rest_framework
from rest_framework import generics, mixins, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from django.http import Http404, HttpResponse
from rest_framework import status, views
from rest_framework.compat import coreapi, coreschema

import utils
from utils.drf import StandardResultsSetPagination, OptionalResultsSetPagination
from utils.json import zeroout_microseconds, parse_bool
from observations.filters import SubjectObjectPermissionsFilter, create_gp_filter_class
from observations.permissions import StandardObjectPermissions
from observations import models
from observations.utils import calculate_subject_view_window, VIEW_SUBJECT_PERMS

import observations.serializers as serializers

from observations import kmlutils

logger = logging.getLogger(__name__)

try:
    days = int(settings.SHOW_TRACK_DAYS)
except AttributeError:
    days = 16

LAST_DAYS = datetime.timedelta(days=days)
ONE_YEAR = datetime.timedelta(days=365)

INCLUDE_STATIONARY_SUBJECTS_ON_MAP = getattr(
    settings, 'SHOW_STATIONARY_SUBJECTS_ON_MAP', False)

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
    return datetime.datetime.now(pytz.utc) - datetime.timedelta(days=days)


def dateparse(date_str, default_tz=pytz.utc):
    dt = dateutil.parser.parse(date_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


class RegionsView(generics.ListAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class RegionView(generics.RetrieveAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class SubjectGroupsView(generics.ListAPIView):
    """
    Returns all subjectgroups in the system.
    """
    serializer_class = serializers.create_sg_serializer('subjectgs', models.SubjectGroup,
                                                        serializers.SubjectSerializer)
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (create_gp_filter_class('subjectgf',
                                              ('observations.view_subjectgroup',),
                                              models.SubjectGroup),)

    def get_queryset(self):
        queryset = models.SubjectGroup.objects.filter(
            _parents=None, is_visible=parse_bool(
                self.request.GET.get('isvisible', True)))
        queryset = queryset.order_by('name')
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['render_last_location'] = True
        return context


class SubjectGroupView(generics.RetrieveAPIView):
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
        return context


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


class RegionSubjectsView(generics.ListAPIView):
    lookup_field = 'slug'
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)

    def get_queryset(self):
        region = generics.get_object_or_404(models.Region.objects.all(),
                                            slug=self.kwargs['slug'])
        subjects = models.Subject.objects.by_region(
            region).annotate_with_subject_status()
        return subjects


from observations.utils import get_minimum_allowed_age, get_maximum_allowed_age


class SubjectsViewSchema(rest_framework.schemas.AutoSchema):

    def get_manual_fields(self, path, method):
        if method == 'GET':
            extra_fields = [
                coreapi.Field(
                    name='tracks_since',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Tracks Since',
                        description='Include tracks since this timestamp',

                    )
                ),
                coreapi.Field(
                    name='tracks_until',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Tracks Until',
                        description='Include tracks up through this timestamp'
                    )
                ),
                coreapi.Field(
                    name='bbox',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Bounding Box',
                        description='Include subjects having track data within this bounding box defined by '
                                    'a 4-tuple of coordinates marking west, south, east, north.',

                    ),
                ),
                coreapi.Field(
                    name='subject_group',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Subject Group ID',
                        description='Indicate a subject group for which Subjects should be listed.',
                        format='UUID'

                    )
                ),
                coreapi.Field(
                    name='name',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Subject name',
                        description='Find subjects with the given name.',
                    )
                ),
                coreapi.Field(
                    name='updated_since',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Updated Since',
                        description='Return Subject that have been updated since the given timestamp.',
                    )
                ),
                coreapi.Field(
                    name='render_last_location',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Subject Group ID',
                        description='Indicate whether to render each subject\'s last location.',
                    )
                ),
                coreapi.Field(
                    name='tracks',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Tracks',
                        description='Indicate whether to render each subject\'s recent tracks.',
                    )
                ),
                coreapi.Field(
                    name='id',
                    required=False,
                    location='query',
                    schema=coreschema.String(
                        title='Subject ID(s)',
                        description='A comma-delimited list of Subject IDs.',
                    )
                ),
            ]
            return super().get_manual_fields(path, method) + extra_fields


class SubjectsView(generics.ListCreateAPIView):
    """
    get:
    Returns a list of Subject in the system.

    """
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = OptionalResultsSetPagination

    TRACK_QPARAMS = ('tracks_limit',)
    TRACK_DATE_QPARAMS = ('tracks_since', 'tracks_until')

    schema = SubjectsViewSchema()

    def get_queryset(self):
        min_age = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects \
            .annotate_with_subjectstatus(delay_hours=min_age * 24)
        # need a stable sort for pagination. this needs to match the distinct
        # parameter set in by_user_subjects
        queryset = queryset.order_by('id')
        queryset = queryset.by_is_active()
        bbox = self.request.query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            queryset = queryset.by_bbox(bbox, last_days=LAST_DAYS,
                                        include_stationary_subjects=INCLUDE_STATIONARY_SUBJECTS_ON_MAP)

        if self.request.query_params.get('name', None):
            queryset = queryset.by_name_search(
                self.request.query_params.get('name'))

        subject_group = self.request.query_params.get('subject_group', None)
        if subject_group:
            groups = models.SubjectGroup.objects.get_nested_groups(
                subject_group)
            queryset = queryset.by_groups(groups)

        # Filter by provided subject_ids.
        subject_ids = self.request.query_params.get('id', '')
        if subject_ids:
            queryset = queryset.by_id(subject_ids)

        queryset = queryset.by_user_subjects(self.request.user)

        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        queryset = queryset.select_related(
            'subject_subtype', 'subject_subtype__subject_type')
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24)

        updated_since = self.request.query_params.get('updated_since', None)
        if updated_since:
            try:
                updated_since = dateparse(updated_since)
            except ValueError:
                raise ValueError(
                    f'Invalid value for updated_since: "{updated_since}"')
            else:
                queryset = queryset.by_updated_since(updated_since)

        return queryset

    def get_serializer_context(self):
        request = self.request
        context = super().get_serializer_context()
        context['render_last_location'] = True
        context['tracks'] = False

        if request and parse_bool(request.query_params.get('tracks', None)):
            context['tracks'] = True
            for t in self.TRACK_QPARAMS:
                context[t] = request.query_params.get(t, None)
            for t in self.TRACK_DATE_QPARAMS:
                context[t] = dateparse(request.query_params.get(
                    t, None)) if request.query_params.get(t, None) else None
        return context


class SubjectView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.SubjectSerializer
    lookup_field = 'id'

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects.all()
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24)
        return queryset


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

        # /{id}/ contains subject_id.
        request.data['subject'] = self.kwargs['id']
        serializer = serializers.SubjectSourceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST, )
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SourceSubjectsView(generics.ListCreateAPIView):
    serializer_class = serializers.SubjectSerializer

    def get_queryset(self):
        source = generics.get_object_or_404(
            models.Source.objects.all(), pk=self.kwargs['id'])
        # if not self.request.user.has_any_perms(models.Source.VIEW_SUBJECT_PERMS, source):
        #     raise PermissionDenied
        return models.Subject.objects.filter(subjectsource__source=source).annotate_with_subjectstatus()

    def create(self, request, *args, **kwargs):
        # /{id}/ contains subject_id.
        request.data['subject'] = self.kwargs['id']
        serializer = serializers.SubjectSourceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST, )
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


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
            since = datetime.datetime.now(tz=pytz.UTC) - LAST_DAYS

        coordinates = []
        times = []
        for ob in models.Observation.objects.get_subject_source_observation_values(sds, since, until):
            coordinates.append(ob['location'].coords)
            times.append(zeroout_microseconds(ob['recorded_at']))

        context['times'] = times
        context['coordinates'] = coordinates
        return context


class TrackLimitSerializer(rest_framework.serializers.Serializer):
    limit = rest_framework.serializers.IntegerField(
        default=None, required=False)


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
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        queryset = models.Subject.objects.all()
        queryset = queryset.annotate_with_subjectstatus(
            delay_hours=min_age_days * 24)
        return queryset

    def check_object_permissions(self, request, obj):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, obj):
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

        context['tracks_since'] = self.request.query_params.get('since', None)
        context['tracks_until'] = self.request.query_params.get('until', None)

        for key in ('tracks_since', 'tracks_until'):
            context[key] = dateparse(context[key]) if context[key] else None

        return context


class ObservationView(generics.RetrieveUpdateDestroyAPIView):
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    lookup_field = 'id'
    queryset = models.Observation.objects.all()
    serializer_class = serializers.ObservationSerializer


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
    filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = StandardResultsSetPagination

    lookup_fields = ('manufacturer_id', 'provider_key')

    def get_queryset(self):
        queryset = models.Source.objects.all()

        filter = {}
        for fn in self.lookup_fields:
            if fn in self.request.query_params:
                filter[fn] = self.request.query_params.get(fn)
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

    lookup_field = 'provider_key'

    def get_queryset(self):
        queryset = models.SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context

    # TODO - filter so only 'additional' can get updated
    def put(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class SourceObservationsView(generics.ListAPIView):
    serializer_class = serializers.ObservationSerializer
    pagination_class = StandardResultsSetPagination

    lookup_field = 'id'

    def get_queryset(self):
        source = generics.get_object_or_404(
            models.Source.objects.all(), pk=self.kwargs['id'])
        observations = models.Observation.objects.filter(source_id=source.id)
        return observations


class ObservationsView(generics.ListCreateAPIView):

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    queryset = models.Observation.objects.all()
    serializer_class = serializers.ObservationSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (StandardObjectPermissions,)

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


class KmlRootView(generics.GenericAPIView):
    renderer_classes = (StaticHTMLRenderer,)

    def build_link_for_user(self):
        token = kmlutils.get_kml_access_token(self.request.user, )
        return utils.add_base_url(self.request,
                                  '?'.join((
                                      reverse('subjects-kml-view'),
                                      'auth={}'.format(token))
                                  )
                                  )

    def get(self, request, *args, **kwargs):
        # TODO: Have a configuration for naming the KML feed.
        filename = 'DAS-KML_{}_{}'.format(self.request.user.username,
                                          datetime.datetime.now(tz=pytz.utc).strftime('%Y%M%d%H%M'))

        context = {'network_link':
                   {'name': settings.KML_FEED_TITLE,
                    'visibility': 0,
                    'open': 1,
                    'href': self.build_link_for_user()
                    }
                   }

        result = render_to_string('kml/user_root.xml', context)

        return kmlutils.render_to_kmz(result, filename)


class KmlSubjectsView(generics.GenericAPIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer,)

    def get_queryset(self):
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        # To include inactive subjects in KmlSubject report
        queryset = models.Subject.objects.all()  # .by_is_active()
        queryset = queryset.by_user_subjects(self.request.user) \
            .annotate_with_subjectstatus(delay_hours=min_age_days * 24)
        return queryset

    def build_link_for_subject(self, subject):
        token = kmlutils.get_kml_access_token(self.request.user)

        return utils.add_base_url(self.request,
                                  '?'.join((
                                      reverse('subject-kml-view',
                                              args=[subject['id']]),
                                      'auth={}'.format(token))
                                  )
                                  )

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
            models.Subject.objects.all(), pk=self.kwargs['id'])
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
        utc = pytz.UTC
        try:
            if self.request.GET.get('start'):
                filter_parameters.update({
                    'start': utc.localize(dateutil.parser.parse(
                        self.request.GET.get('start')))})
        except (ValueError, TypeError):
            raise ValueError('Invalid start-date format - {}'.format(
                self.request.GET.get('start')))
        try:
            if self.request.GET.get('end'):
                filter_parameters.update({
                    'end': utc.localize(dateutil.parser.parse(
                        self.request.GET.get('end')))})
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
        }
        result = render_to_string('kml/subject_track.xml', context)
        return kmlutils.render_to_kmz(result, filename)


class TrackingDataCsvView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)

    def get_queryset(self, chronofile=None):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise PermissionDenied
        queryset = models.Subject.objects.all()
        # To include inactive subjects in trackingdata report
        # queryset = queryset.by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
        if chronofile is not None:
            queryset = queryset.filter(
                subjectsource__additional__chronofile=int(chronofile))
        return queryset

    def get(self, request, *args, **kwargs):
        # Set exclusion flag value
        filter_flag = 0
        try:
            if self.request.GET.get('filter'):
                filter_flag = int(self.request.GET.get('filter', 0))
        except (ValueError, TypeError):
            filter_flag = 0

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

        # return in json format or csv
        format = self.request.GET.get('format', '').lower()

        # get data for a specific chronofile? This is for STE downloader
        request_subject_chronofile = self.request.GET.get(
            'subject_chronofile', None)

        # get current status? or historical observations
        get_current = self.request.GET.get(
            'current_status', 'false').lower() == 'true'

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
            tz_offset) if format != 'json' else 'fixtime'
        dloadtime_label = 'dloadtime ({})'.format(
            tz_offset) if format != 'json' else 'dloadtime'
        fieldnames = ['chronofile', 'recordserial', 'collar_id', fixtime_label, dloadtime_label,
                      'lon', 'lat', 'height', 'temp']
        csv_data = []
        cur_record_serial = record_serial_base
        if get_current is True:
            # all the current status objects for the allowed subjects
            items = self.get_subject_status_queryset(max_records)
            if items:
                for item in items:
                    cur_record_serial += 1
                    data = self.get_csv_observation_data(cur_record_serial, dloadtime_label, fixtime_label, format,
                                                         item, request_subject_chronofile)
                    csv_data.append(data)
        else:
            subjects = self.get_queryset(request_subject_chronofile)
            for subject in subjects:
                # all the relevant observations for the subject (or chronofile)
                items = self.get_subject_trackdata_queryset(
                    filter_flag, lower, subject, upper, max_records, request_subject_chronofile)

                if items:
                    for item in items:
                        cur_record_serial += 1
                        data = self.get_csv_observation_data(cur_record_serial, dloadtime_label, fixtime_label, format,
                                                             item, request_subject_chronofile)
                        csv_data.append(data)

        # Generate CSV attachment and send it with response
        timestamp = current_tz.localize(datetime.datetime.utcnow())

        if format == 'json':
            return HttpResponse(
                json.dumps({'data': csv_data}, cls=DjangoJSONEncoder),
                content_type='application/json', status=status.HTTP_200_OK
            )

        download_filename = f'Tracking Data {timestamp.strftime("%Y-%m-%d")}.csv'
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment;filename={download_filename}'
        response['x-das-download-filename'] = download_filename

        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        if csv_data:
            writer.writerows(csv_data)
        return response

    def get_csv_observation_data(self, cur_record_serial, dloadtime_label, fixtime_label, format, item,
                                 request_subject_chronofile):
        recorded_at = item['recorded_at'].astimezone(
            current_tz) if format != 'json' else item['recorded_at']
        created_at = item['created_at'].astimezone(
            current_tz) if format != 'json' else item['created_at']
        chronofile = request_subject_chronofile if request_subject_chronofile is not None \
            else item['subjectsource_additional'].get('chronofile', '') \
            if item['subjectsource_additional'] else ''
        collar_id = item['collar_id']
        if chronofile:
            pass
        data = {'lat': item['location'].x,
                'lon': item['location'].y,
                'height': item['location'].z,
                'chronofile': chronofile,
                'collar_id': collar_id,
                'recordserial': cur_record_serial,
                fixtime_label: recorded_at.strftime('%m/%d/%Y %H:%M:%S') if format != 'json'
                else recorded_at.isoformat(),
                dloadtime_label: created_at.strftime('%m/%d/%Y %H:%M:%S') if format != 'json'
                else created_at.isoformat(),
                'temp': item['additional'].get('temp', 0)
                }
        return data

    def get_subject_trackdata_queryset(self, filter_flag, lower, subject, upper, max_records, request_subject_chronofile):
        qs = models.Observation.objects.all()
        if request_subject_chronofile is not None:
            # NOTE: time bounds are EXCLUSIVE
            qs = qs.filter(exclusion_flags=filter_flag,
                           recorded_at__gt=lower,
                           recorded_at__lt=upper,
                           source__subjectsource__assigned_range__contains=F(
                               'recorded_at'),
                           source__subjectsource__additional__chronofile=int(request_subject_chronofile))
        else:
            qs = qs.filter(exclusion_flags=filter_flag,
                           recorded_at__gt=lower,
                           recorded_at__lt=upper,
                           source__subjectsource__assigned_range__contains=F(
                               'recorded_at'),
                           source__subjectsource__subject=subject)
        qs = qs.annotate(subjectsource_additional=F('source__subjectsource__additional'),
                         collar_id=F('source__manufacturer_id')).order_by('recorded_at').values()

        if max_records > 0:
            qs = qs[:max_records]
        return qs

    def get_subject_status_queryset(self, max_records):
        now = pytz.utc.localize(datetime.datetime.utcnow())
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        qs = models.SubjectStatus.objects.filter(delay_hours=min_age_days * 24)\
            .filter(subject__subjectsource__additional__chronofile__isnull=False,
                    subject__subjectsource__assigned_range__contains=now) \
            .annotate(subjectsource_additional=F('subject__subjectsource__additional'),
                      collar_id=F('subject__subjectsource__source__manufacturer_id')).values()
        if max_records > 0:
            qs = qs[:max_records]
        return qs


class TrackingMetaDataExportView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)

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
                   'frequency', 'animal_id', 'name', 'species',
                   data_starts, data_stops,
                   'date_off_or_removed', 'comments',
                   'predicted_expiry', 'rgb', 'sex', 'gmt', 'data_status',
                   'data_starts_source', 'data_stops_source',
                   'data_stops_reason', 'collar_status', 'collar_model',
                   'has_acc_data', 'data_owners', 'region', 'country']

        # NOTE: nearly all the data for this call is actually found in the source and subject source, however
        #       it is the subject and by association the subject_group that are limited by the user
        #       so make sure to get the source the is currently assigned
        now = pytz.utc.localize(datetime.datetime.utcnow())
        subjects = self.get_queryset()
        subjects = subjects.annotate(ss=FilteredRelation('subjectsource',
                                                         condition=Q(subjectsource__assigned_range__contains=now)))\
            .annotate(subjectsource_additional=F('ss__additional'))\
            .annotate(source_model_name=F('ss__source__model_name'))\
            .annotate(source_manufacturer_id=F('ss__source__manufacturer_id'))\
            .annotate(subjectsource_assigned_range=F('ss__assigned_range'))\
            .annotate(source_additional=F('ss__source__additional'))

        for subject in subjects:
            subject.subjectsource_additional = {} if subject.subjectsource_additional is None \
                else subject.subjectsource_additional

            source_details = {}
            try:
                # Collect Subject details.
                source_details.update({
                    'name': subject.name,
                    'species': subject.additional.get('species', ''),
                    'rgb': subject.additional.get('rgb', ''),
                    'sex': subject.additional.get('sex', ''),
                    'region': subject.additional.get('region', ''),
                    'country': subject.additional.get('country', '')})

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
                        'active': subject.source_additional.get('active', ''),
                        'frequency': subject.source_additional.get(
                            'frequency', ''),
                        'animal_id': subject.source_additional.get(
                            'tm_animal_id', ''),
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
                        'collar_status':
                            subject.source_additional.get('collar_status', ''),
                        'collar_model': subject.source_additional.get(
                            'collar_model', ''),
                        'has_acc_data': subject.source_additional.get(
                            'has_acc_data', ''),
                        'data_owners': subject.source_additional.get(
                            'data_owners', '')
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
        # queryset = queryset.by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
        return queryset
