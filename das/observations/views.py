import logging
import datetime

import dateutil.parser
import pytz
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.http import Http404
from django.db.models import Prefetch
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, DjangoObjectPermissions
from rest_framework.response import Response
from rest_framework.filters import DjangoObjectPermissionsFilter
from django.http import Http404
from rest_framework import status

from utils.drf import StandardResultsSetPagination
from utils.json import zeroout_microseconds
from observations.filters import SubjectObjectPermissionsFilter, create_gp_filter_class
from observations.permissions import StandardObjectPermissions
from observations import models
import observations.serializers as serializers

logger = logging.getLogger(__name__)


try:
    days = int(settings.SHOW_TRACK_DAYS)
except AttributeError:
    days = 16

LAST_DAYS = datetime.timedelta(days=days)


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
        queryset = models.SubjectGroup.objects.filter(_parents=None)
        queryset = queryset.order_by('name')
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['render_last_location'] = True
        return context


class SubjectGroupView(generics.ListAPIView):
    """
    Returns a single SubjectGroup
    """
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
        return queryset


class RegionSubjectsView(generics.ListAPIView):
    lookup_field = 'slug'
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)

    def get_queryset(self):
        region = generics.get_object_or_404(models.Region.objects.all(),
                                            slug=self.kwargs['slug'])
        subjects = models.Subject.objects.by_region(region)
        return subjects


class SubjectsView(generics.ListCreateAPIView):
    """
    Returns all subjects in the system.
    Optional qparam of:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    """
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = models.Subject.objects.all()
        queryset = queryset.by_is_active()
        bbox = self.request.query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            queryset = queryset.by_bbox(bbox, last_days=LAST_DAYS)
        subject_group = self.request.query_params.get('subject_group', None)
        if subject_group:
            queryset = queryset.by_user_subjects(self.request.user)
        queryset = queryset.prefetch_related(Prefetch('subjectstatus_set'))
        return queryset


    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['render_last_location'] = True
        return context


class SubjectView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.SubjectSerializer
    lookup_field = 'id'

    def get_queryset(self):
        queryset = models.Subject.objects.all()
        queryset = queryset.prefetch_related(Prefetch('subjectstatus_set'))
        return queryset


# class SubjectObservationsView(generics.ListCreateAPIView):
#
#     serializer_class = serializers.ObservationSerializer
#     pagination_class = StandardResultsSetPagination
#
#     lookup_field = 'id'
#
#     def _find_source(self, subject_id):
#         try:
#             subject = generics.get_object_or_404(models.Subject.objects.all(), id=subject_id)
#
#             ss = subject.subjectsource_set.all().first()
#
#             if ss:
#                 return ss.source
#         except:
#             return None
#
#     def create(self, request, *args, **kwargs):
#         '''
#          On condition of post body being a list, let it bulk insert.
#         :param request:
#         :param args:
#         :param kwargs:
#         :return:
#         '''
#
#         request_data = request.data if isinstance(request.data, list) else [request.data,]
#         source = self._find_source(kwargs['id'])
#         request_data = [r.update({'source_id':source.id}) for r in request_data]
#         serializer = serializers.ObservationSerializer(many=True, data=request_data)
#         serializer.is_valid(raise_exception=True)
#         self.perform_create(serializer)
#         headers = self.get_success_headers(serializer.data)
#         return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
#
#     def get_queryset(self):
#         try:
#             subject = generics.get_object_or_404(models.Subject.objects.all(), pk=self.kwargs['id'])
#             subject_sources = models.SubjectSource.objects.get_subject_sources(subject)
#             sources = models.Source.objects.filter(pk__in=subject_sources.values('source'))
#             source = sources.first()
#             observations = models.Observation.objects.filter(source_id=source.id)
#             return observations
#         except:
#             return models.Observation.objects.none()
#
class SubjectSourcesView(generics.ListAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        subject_sources = models.SubjectSource.objects.get_subject_sources(subject)
        sources = models.Source.objects.filter(pk__in=subject_sources.values('source'))
        return sources


class SubjectSourceView(generics.RetrieveAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS, subject):
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
    queryset = models.Subject.objects.all()
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

        sds = models.SubjectSource.objects.get_subject_source(subject, source_id)
        if not sds:
            raise Http404

        if since is None:
            since = datetime.datetime.now(tz=pytz.UTC) - LAST_DAYS

        coordinates = []
        times = []
        for ob in models.Observation.objects.get_source_range_observation_values(
                sds, since, until):
            coordinates.append(ob['location'].coords)
            times.append(zeroout_microseconds(ob['recorded_at']))

        context['times'] = times
        context['coordinates'] = coordinates
        return context


class SubjectTracksView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)
    lookup_field = 'id'
    serializer_class = serializers.TrackSerializer
    queryset = models.Subject.objects.all()

    def get_object(self):
        try:
            return self._cached_object
        except AttributeError:
            pass
        self._cached_object = super().get_object()

        return self._cached_object

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        response = Response(data)
        return response

    def get_serializer_context(self):
        context = super().get_serializer_context()
        subject = self.get_object()

        # Get all the arguments
        limit = self.request.query_params.get('limit', None)
        until = self.request.query_params.get('until', datetime.datetime.now(tz=pytz.UTC))
        since = self.request.query_params.get('since', datetime.datetime.now(tz=pytz.UTC) - LAST_DAYS)

        # Since and until could be passed as strings
        if until and isinstance(until, str):
            until = dateparse(until)
        if since and isinstance(since, str):
            since = dateparse(since)

        # Apply permissions
        if self.request.user.has_any_perms(models.Subject.VIEW_POSITION_PERMS, subject):
            context['subject'] = subject
            try:
                context['subject_state'] = subject.subjectstatus_set.get_last().additional['state']
            except Exception:
                pass
        elif self.request.user.has_any_perms(models.Subject.VIEW_DELAYED_PERMS, subject):
            # Make sure the date ranges are delayed
            one_day = datetime.timedelta(hours=24)
            until = min(until,datetime.datetime.now(tz=pytz.UTC) - one_day)
            since = min(since, datetime.datetime.now(tz=pytz.UTC) - one_day)
            if since >= until:
                return None
            try:
                context['subject_state'] = subject.subjectstatus_set.get_delayed().additional['state']
            except Exception:
                pass
        else:
            return None

        sds = models.SubjectSource.objects.filter(subject=subject)
        if not sds:
            raise Http404

        coordinates = []
        times = []
        for ob in models.Observation.objects.get_source_range_observation_values(
                sds, since=since, until=until, limit=limit):
            coordinates.append(ob['location'].coords)
            times.append(zeroout_microseconds(ob['recorded_at']))

        context['times'] = times
        context['coordinates'] = coordinates
        return context


class ObservationView(generics.RetrieveUpdateDestroyAPIView):
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    lookup_field = 'id'
    queryset = models.Observation.objects.all()
    serializer_class = serializers.ObservationSerializer


class SourceView(generics.RetrieveUpdateDestroyAPIView, generics.CreateAPIView):
    lookup_field = 'id'
    queryset = models.Source.objects.all()
    serializer_class = serializers.SourceSerializer

class SourcesView(generics.ListCreateAPIView):
    serializer_class = serializers.SourceSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = models.Source.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class SourceObservationsView(generics.ListAPIView):

    serializer_class = serializers.ObservationSerializer
    pagination_class = StandardResultsSetPagination

    lookup_field = 'id'

    def get_queryset(self):
        source = generics.get_object_or_404(models.Source.objects.all(), pk=self.kwargs['id'])
        observations = models.Observation.objects.filter(source_id=source.id)
        return observations


class ObservationsView(generics.ListCreateAPIView):
    queryset = models.Observation.objects.all()
    serializer_class = serializers.ObservationSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        '''
         On condition of post body being a list, let it bulk insert.
        :param request:
        :param args:
        :param kwargs:
        :return:
        '''
        serializer = serializers.ObservationSerializer(many=isinstance(request.data, list), data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST,)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
