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

from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.db.models import Prefetch
from rest_framework import generics, mixins, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from django.http import Http404, HttpResponse
from rest_framework import status, views

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


class SourceGroupDetailsView(generics.ListAPIView):
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
        subjects = models.Subject.objects.by_region(region)
        return subjects


class SubjectsView(generics.ListCreateAPIView):
    """
    Returns all subjects in the system.
    Optional qparam of:
    page_size enable paging of subjects, sets the page size of subjects returned
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    subject_group   id of subject group
    tracks [true,false] return track with subject resource. Default false. Returns the site wide setting number of days
    track_since starting date range for the requested track, default follow the tracks logic of returning x number of days. ISO date/time
    track_until stop date range for the requested track, default is now. ISO date/time
    """
    serializer_class = serializers.SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)
    pagination_class = OptionalResultsSetPagination

    TRACK_QPARAMS = ('tracks_limit',)
    TRACK_DATE_QPARAMS = ('tracks_since', 'tracks_until')

    def get_queryset(self):
        queryset = models.Subject.objects.all()
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
            queryset = queryset.by_bbox(bbox, last_days=LAST_DAYS)
        subject_group = self.request.query_params.get('subject_group', None)
        if subject_group:
            groups = models.SubjectGroup.objects.get_nested_groups(
                subject_group)
            queryset = queryset.by_groups(groups)
        queryset = queryset.by_user_subjects(self.request.user)
        queryset = queryset.prefetch_related(
            Prefetch('subjectstatus_set')).prefetch_related('subject_subtype')
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

        queryset = models.Subject.objects.all()
        queryset = queryset.prefetch_related(Prefetch('subjectstatus_set'))
        return queryset


class SubjectSourcesView(generics.ListCreateAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
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
        return models.Subject.objects.filter(subjectsource__source=source)

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
            models.Subject.objects.all(), pk=self.kwargs['id'])
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
        queryset = models.Subject.objects.all()
        queryset = queryset.prefetch_related(Prefetch('subjectstatus_set'))
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
        context['tracks_limit'] = self.request.query_params.get('limit', None)
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


class SourcesView(generics.ListCreateAPIView,):
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


class SourceProvidersView(generics.ListCreateAPIView,):
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
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST,)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class KmlRootView(generics.GenericAPIView):
    renderer_classes = (StaticHTMLRenderer,)

    def build_link_for_user(self):

        token = kmlutils.get_kml_access_token(self.request.user,)
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
    renderer_classes = (StaticHTMLRenderer, )

    def get_queryset(self):
        queryset = models.Subject.objects.all().by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
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
                         'region': subject.get('additional').get('region', DEFAULT_REGION_NAME),
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
    renderer_classes = (StaticHTMLRenderer, )
    lookup_field = 'id'

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS,
                                               subject):
            raise PermissionDenied

        queryset = models.Subject.objects.all()
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
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
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

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise PermissionDenied
        queryset = models.Subject.objects.all()
        queryset = queryset.by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
        return queryset

    def get(self, request, *args, **kwargs):
        # Set exclusion flag value
        filter_flag = 0
        try:
            if self.request.GET.get('filter'):
                filter_flag = int(self.request.GET.get('filter', 0))
        except (ValueError, TypeError):
            filter_flag = 0

        # Time range to query observation data according to user's permission
        max_days = 36500  # View All time days permission's number of days
        (lower, upper) = calculate_subject_view_window(
            self.request.user, max_days)
        if lower >= upper:
            raise PermissionDenied

        # Get SubjectSource and Observations with in time range for subjects
        csv_data = []
        fieldnames = ['chronofile', 'recordserial', 'fixtime', 'dloadtime',
                      'lon', 'lat', 'height', 'temp']
        subjects = self.get_queryset()
        for subject in subjects:
            observations = models.Observation.objects.filter(
                source__subjectsource__subject=subject,
                exclusion_flags=filter_flag, recorded_at__range=[lower, upper])
            if observations:
                for observation in observations.all():
                    subject_source = models.SubjectSource.objects.filter(
                        source=observation.source,
                        subject=subject)[0]
                    data = {'lat': observation.location.x,
                            'lon': observation.location.y,
                            'height': observation.location.z,
                            'chronofile': subject_source.additional.get(
                                'chronofile', '') if subject_source.additional else '',
                            'recordserial': observation.id,
                            'fixtime': observation.recorded_at.strftime(
                                '%m/%d%Y %H:%M:%S'),
                            'dloadtime': observation.created_at.strftime(
                                '%m/%d%Y %H:%M:%S'),
                            'temp': observation.additional.get('temp', '')
                            }
                    csv_data.append(data)

        # Generate CSV attachment and send it with response
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.datetime.utcnow())

        if self.request.GET.get('format', '').lower() == 'json':
            return HttpResponse(
                json.dumps({'data': csv_data}, cls=DjangoJSONEncoder),
                content_type='application/json', status=status.HTTP_200_OK
            )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment;' \
                                          'filename=Tracking Data {}.csv'.\
            format(timestamp.strftime('%Y-%m-%d'))
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        if csv_data:
            writer.writerows(csv_data)
        return response


class TrackingMetaDataExportView(generics.RetrieveAPIView):

    permission_classes = (StandardObjectPermissions,)

    def get_source_details(self):
        """
        Gather required details for each Subject/Source combination.
        :return: List of dictionaries containing required details.
        """
        tracking_metadata = []
        headers = ['chronofile', 'collar_type', 'collar_id', 'active',
                   'frequency', 'animal_id', 'name', 'species', 'data_starts',
                   'data_stops', 'date_off_or_removed', 'comments',
                   'predicted_expiry', 'rgb', 'sex', 'gmt', 'data_status',
                   'data_starts_source', 'data_stops_source',
                   'data_stops_reason', 'collar_status', 'collar_model',
                   'has_acc_data', 'data_owners', 'region', 'country']

        for subject in self.get_queryset():
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

                if subject.source:
                    # Collect Source details.

                    # TODO: Validate this assumption that the "first" record is
                    # the right one.
                    subject_source = models.SubjectSource.objects.\
                        get_subject_source(subject, subject.source.id).first()

                    source_details.update({
                        'chronofile': subject_source.additional.get(
                            'chronofile', ''),
                        'collar_type': subject.source.model_name,
                        'collar_id': subject.source.manufacturer_id,
                        'active': subject.source.additional.get('active', ''),
                        'frequency': subject.source.additional.get(
                            'frequency', ''),
                        'animal_id': subject.source.additional.get(
                            'tm_animal_id', ''),
                        'data_starts': subject_source.safe_assigned_range.lower,
                        'data_stops': subject_source.safe_assigned_range.upper,
                        'comments': subject_source.additional.get(
                            'comments', ''),
                        'predicted_expiry':
                            subject.source.additional.get(
                                'predicted_expiry', ''),
                        'data_status': subject_source.additional.get(
                            'data_status', ''),
                        'data_starts_source':
                            subject_source.additional.get(
                                'data_starts_source', ''),
                        'data_stops_source':
                            subject_source.additional.get(
                                'data_stops_source', ''),
                        'data_stops_reason':
                            subject_source.additional.get(
                                'data_stops_reason', ''),
                        'collar_status':
                            subject.source.additional.get('collar_status', ''),
                        'collar_model': subject.source.additional.get(
                            'collar_model', ''),
                        'has_acc_data': subject.source.additional.get(
                            'has_acc_data', ''),
                        'data_owners': subject.source.additional.get(
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
        tracking_metadata, headers = self.get_source_details()

        if self.request.GET.get('format', '').lower() == 'json':
            return HttpResponse(
                json.dumps({'metadata': tracking_metadata},
                           cls=DjangoJSONEncoder),
                content_type='application/json', status=status.HTTP_200_OK
            )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=' \
            '"Tracking Meta Data Export {}.csv"'.format(
            timestamp.strftime('%Y-%m-%d'))

        writer = csv.DictWriter(response, headers)
        writer.writeheader()
        writer.writerows(tracking_metadata)
        return response

    def get_queryset(self):
        # Get user accessible active subjects.
        queryset = models.Subject.objects.all()
        queryset = queryset.by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
        return queryset
