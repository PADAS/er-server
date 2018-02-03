import logging
import datetime
import zipfile
import dateutil.parser
import pytz
from io import BytesIO
import re

from django.conf import settings
from django.urls import reverse

from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from django.http import Http404
from rest_framework import status


import utils
from utils.drf import StandardResultsSetPagination
from utils.json import zeroout_microseconds
from observations.filters import SubjectObjectPermissionsFilter, create_gp_filter_class
from observations.permissions import StandardObjectPermissions
from observations import models
from observations.utils import calculate_subject_view_window

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
        queryset = models.SubjectGroup.objects.filter(_parents=None)
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
    #pagination_class = StandardResultsSetPagination

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
            queryset = queryset.by_group(subject_group_id=subject_group.id)
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
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        queryset = models.Subject.objects.all()
        queryset = queryset.prefetch_related(Prefetch('subjectstatus_set'))
        return queryset


class SubjectSourcesView(generics.ListCreateAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS, subject):
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
    # permission_classes = (StandardObjectPermissions,)
    lookup_field = 'subject_id'
    serializer_class = serializers.TrackSerializer

    # TODO: Fix this so it accounts for the authenticated user's view-window
    # permissions.
    queryset = models.SubjectStatus.objects.filter(
        delay_hours=0).prefetch_related('subject')

    def get_object(self):
        try:
            return self._cached_object
        except AttributeError:
            pass
        self._cached_object = super().get_object()

        return self._cached_object

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance.subject)
        data = serializer.data
        response = Response(data)
        return response

    def get_serializer_context(self):
        context = super().get_serializer_context()

        subjectstatus = self.get_object()
        subject = subjectstatus.subject

        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        # Max number of observations in the track
        limit = self.request.query_params.get('limit', None)

        # Find the min and max boundaries for track data
        oldest_age_allowed = -1
        newest_age_allowed = 999
        mou_expiry_date = self.request.user.additional.get('expiry', None)

        for permission_tuple in sorted(models.Subject.VIEW_BEGIN_WINDOWS, key=lambda _: _[1], reverse=True):
            if permission_tuple[1] > oldest_age_allowed and self.request.user.has_perm(permission_tuple[0]):
                oldest_age_allowed = permission_tuple[1]
                break

        for permission_tuple in sorted(models.Subject.VIEW_END_WINDOWS, key=lambda _: _[1]):
            if permission_tuple[1] < newest_age_allowed and self.request.user.has_perm(permission_tuple[0]):
                newest_age_allowed = permission_tuple[1]
                break

        if oldest_age_allowed < 0 or newest_age_allowed > oldest_age_allowed:
            raise PermissionDenied

        requested_oldest_age = self.request.query_params.get('since', None)
        requested_newest_age = self.request.query_params.get('until', None)
        now = pytz.utc.localize(datetime.datetime.utcnow())

        if requested_oldest_age is None:
            oldest_age = min(settings.SHOW_TRACK_DAYS, oldest_age_allowed)
        else:
            requested_oldest_age = (now - requested_oldest_age).days
            oldest_age = min(requested_oldest_age, oldest_age_allowed)

        if requested_newest_age is None:
            newest_age = newest_age_allowed
        else:
            requested_newest_age = (now - requested_newest_age).days
            newest_age = max(requested_newest_age, newest_age_allowed)

        if mou_expiry_date is not None:
            now = pytz.utc.localize(datetime.datetime.utcnow())
            mou_expiry_date = pytz.utc.localize(
                dateutil.parser.parse(mou_expiry_date))
            mou_expiry_age = now - mou_expiry_date

            newest_age = max(mou_expiry_age.days, newest_age)
            if oldest_age < newest_age:
                raise PermissionDenied

        begin = now - datetime.timedelta(days=oldest_age)
        until = now - datetime.timedelta(days=newest_age)

        context['subject'] = subject
        try:
            # ss = models.SubjectStatus.objects.get(subject=subject, delay_hours=0)
            # for k in ('last_voice_call_start_at', 'requested_location_at'):
            #     if k in ss.additional:
            #         context[k] = ss.additional[k]
            ss = subjectstatus
            # TODO: Investigate why we use the alternative key for 'state'
            if 'state' in ss.additional:
                context['subject_state'] = ss.additional['state']

        except models.SubjectStatus.DoesNotExist:
            pass

        coordinates = []
        times = []

        qs = models.Observation.objects.get_subject_observations_values(subject,
                                                                        since=begin, until=until, limit=limit)

        # for ob in qs:
        #     coordinates.append(ob['location'].coords)
        #     times.append(zeroout_microseconds(ob['recorded_at']))

        qs = list(qs)
        # context['times'] = [zeroout_microseconds(o.recorded_at) for o in qs]
        # context['coordinates'] = [o.location.coords for o in qs]
        context['times'] = [zeroout_microseconds(o['recorded_at']) for o in qs]
        context['coordinates'] = [o['location'].coords for o in qs]

        # context['times'] = times
        # context['coordinates'] = coordinates
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

    lookup_fields = ('manufacturer_id', 'provider_name')

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

    lookup_field = 'name'

    def get_queryset(self):
        queryset = models.SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


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
        return models.Subject.SUBTYPE_DISPLAY_NAMES.get(subtype, 'Unassigned')

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
        if not self.request.user.has_any_perms(models.Subject.VIEW_SUBJECT_PERMS,
                                               subject):
            raise PermissionDenied

        queryset = models.Subject.objects.all()
        return queryset

    def get_subject_color(self, subject):

        try:
            r, g, b = subject.additional['rgb'].split(',')
        except:
            r, g, b = (0, 0, 0)

        return rgb_to_hex(r, g, b)

    def get_allowed_subject_observations(self, subject):
        (lower, upper) = calculate_subject_view_window(self.request.user)

        if lower >= upper:
            raise PermissionDenied

        return models.Observation.objects.get_subject_observations_values(subject, since=lower, until=upper)

    def get(self, request, *args, **kwargs):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        self.check_object_permissions(self.request, subject)

        observations = list(self.get_allowed_subject_observations(subject))

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
