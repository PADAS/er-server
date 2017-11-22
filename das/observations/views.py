import logging
import datetime
import zipfile
import dateutil.parser
import pytz
import sys
from io import BytesIO

from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.http import Http404
from django.core.urlresolvers import reverse
from django.db.models import Prefetch
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from rest_framework.filters import DjangoObjectPermissionsFilter
from django.http import Http404
from rest_framework import status
from shapely.geometry import Point, LineString
import simplekml

import utils
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
    permission_classes = (StandardObjectPermissions,)
    lookup_field = 'subject_id'
    serializer_class = serializers.TrackSerializer
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

        qs = models.Observation.objects.get_subject_observations(
            subject, since=begin, until=until)[:limit].values('location', 'recorded_at')

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


def render_to_kmz(kml_str, filename):
    full_filename = '{}.kmz'.format(filename)
    zip_io = BytesIO()
    with zipfile.ZipFile(zip_io, mode='w', compression=zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('document.kml', kml_str.encode('utf-8'))
    response = Response(zip_io.getvalue(),
                        content_type='application/vnd.google-earth.kmz')
    response['Content-Disposition'] = 'attachment; filename={}'.format(
        full_filename)
    response['x-das-download-filename'] = full_filename
    response['Content-Length'] = zip_io.tell()
    return response


class KmlMasterSubjectsView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    renderer_classes = (StaticHTMLRenderer,)

    def build_link_for_user(self):
        token = self.request.user.get_kml_access_token()
        return utils.add_base_url(self.request,
                                  '?'.join((
                                      reverse('subjects-kml-view'),
                                      'auth={}'.format(token))
                                  )
                                  )

    def get(self, request, *args, **kwargs):
        k = simplekml.Kml()

        # TODO: Have a configuration for naming the KML feed.
        k.document = k.newfolder(
            name='STE Tracking Service', visibility=1, open=1)
        link = k.document.newnetworklink(name='STE Tracking Service', open=1)
        link.link.href = self.build_link_for_user()

        filename = 'Master_{}_{}'.format(self.request.user.username,
                                         datetime.datetime.utcnow().strftime('%Y%M%d%H%M'))

        return render_to_kmz(k.kml(), filename)


class KmlSubjectsView(generics.GenericAPIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer, )

    def get_queryset(self):
        queryset = models.Subject.objects.all().by_is_active()
        queryset = queryset.by_user_subjects(self.request.user)
        return queryset

    def build_link_for_subject(self, subject):
        token = self.request.user.get_kml_access_token()

        return utils.add_base_url(self.request,
                                  '?'.join((
                                      reverse('subject-kml-view',
                                              args=[subject['id']]),
                                      'auth={}'.format(token))
                                  )
                                  )

    def get(self, request, *args, **kwargs):
        k = simplekml.Kml()
        k.document = k.newfolder(name='Tracking Data', visibility=1)

        subjects = list(self.get_queryset().values(
            'additional', 'name', 'id', 'subject_type', 'subject_subtype'))

        DEFAULT_REGION_NAME = 'Unknown Region'

        accum = {}
        for sub in subjects:
            speciesf = accum.setdefault(sub.get('subject_subtype'), {})
            regionf = speciesf.setdefault(
                sub.get('additional').get('region', DEFAULT_REGION_NAME), [])
            regionf.append(sub)

        for species, v1 in accum.items():

            speciesf = k.document.newfolder(name=species)

            for region, v2 in sorted(v1.items(), key=lambda x: x[0]):
                regionf = speciesf.newfolder(name=region)

                for subject in sorted(v2, key=lambda x: x['name']):
                    link = regionf.newnetworklink(
                        name=subject['name'], visibility=0)
                    link.link.href = self.build_link_for_subject(subject)

        filename = 'Master{}'.format(
            datetime.datetime.utcnow().strftime('%Y%M%d%H%M'))
        return render_to_kmz(k.kml(), filename)


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
        if 'rgb' in subject.additional:
            r, g, b = subject.additional['rgb'].split(',')
            return rgb_to_hex(r, g, b)
        return None

    def get_subject_icon(self, subject):
        return utils.add_base_url(self.request, subject.image_url)

    def get_allowed_subject_observations(self, subject):
        oldest_age = -1
        newest_age = 999
        mou_expiry_date = self.request.user.additional.get('expiry', None)
        now = datetime.datetime.now(tz=pytz.utc)

        for permission_tuple in sorted(models.Subject.VIEW_BEGIN_WINDOWS,
                                       key=lambda _: _[1], reverse=True):
            if permission_tuple[
                1] > oldest_age and self.request.user.has_perm(
                    permission_tuple[0]):
                oldest_age = permission_tuple[1]
                break

        for permission_tuple in sorted(models.Subject.VIEW_END_WINDOWS,
                                       key=lambda _: _[1]):
            if permission_tuple[
                1] < newest_age and self.request.user.has_perm(
                    permission_tuple[0]):
                newest_age = permission_tuple[1]
                break

        if mou_expiry_date is not None:
            mou_expiry_date = pytz.utc.localize(
                dateutil.parser.parse(mou_expiry_date))
            mou_expiry_age = now - mou_expiry_date

            newest_age = max(mou_expiry_age.days, newest_age)
            if oldest_age < newest_age:
                raise PermissionDenied

        begin = now - datetime.timedelta(days=oldest_age)
        until = now - datetime.timedelta(days=newest_age)

        return models.Observation.objects.get_subject_observations(
            subject, since=begin, until=until).values('location', 'recorded_at')

    def add_points_document(self, folder, subject, observations):
        document = folder.newdocument(
            name='{0}_points'.format(subject.name), visibility=1)

        color = self.get_subject_color(subject)
        style = simplekml.Style()
        style._id = '{0}_Pointstyle'.format(subject.name.replace(' ', '_'))
        style.iconstyle = simplekml.IconStyle(color=color, scale=0.7, icon=simplekml.Icon(
            href=self.get_subject_icon(subject)))
        style.labelstyle = simplekml.LabelStyle(scale=0)
        document.styles.append(style)

        for obs in observations:
            timestamp = obs['recorded_at'].strftime('%Y-%m-%d %H:%M')
            point = document.newpoint()
            point.coords = [(obs['location'].x, obs['location'].y)]
            point.timestamp.when = timestamp
            point.placemark.name = ''
            point.placemark.snippet = simplekml.Snippet(timestamp)
            point.placemark.description = timestamp
            point.style = style

    def add_tracks_document(self, folder, subject, observations):
        document = folder.newdocument(
            name='{0}_tracks'.format(subject.name), visibility=1)

        color = self.get_subject_color(subject)
        style = simplekml.Style()
        style._id = '{0}_Linestyle'.format(subject.name.replace(' ', '_'))
        style.linestyle = simplekml.LineStyle(color=color, width=0.4)
        document.styles.append(style)

        self.last_obs = None
        for obs in observations:
            if self.last_obs is not None:
                line = document.newlinestring()
                line.coords = (([self.last_obs['location'].x, self.last_obs['location'].y, 0], [
                               obs['location'].x, obs['location'].y, 0]))
                line.extrude = 0
                line.tessellate = 1
                line.placemark.name = ''
                line.style = style
            self.last_obs = obs

    def add_position_document(self, folder, subject, observations):

        last_obs = sorted(
            observations, key=lambda x: x['recorded_at'], reverse=True)[0]

        timestamp = last_obs['recorded_at'].strftime('%Y-%m-%d %H:%M')

        color = self.get_subject_color(subject)
        document = folder.newdocument(
            name='{0}\' Last Position'.format(subject.name), visibility=1)

        sh_style = simplekml.Style()
        sh_style._id = 'sh_{0}_Finalmarkerstyle'.format(
            subject.name.replace(' ', '_'))
        sh_style.iconstyle = simplekml.IconStyle(color=color, scale=0.7, icon=simplekml.Icon(
            href=self.get_subject_icon(subject)))
        sh_style.labelstyle = simplekml.LabelStyle(scale=1, color=color)
        sh_style.balloonstyle = simplekml.BalloonStyle(
            bgcolor=color, text='$[description')
        document.styles.append(sh_style)

        sn_style = simplekml.Style()
        sn_style._id = 'sn_{0}_Finalmarkerstyle'.format(
            subject.name.replace(' ', '_'))
        sn_style.iconstyle = simplekml.IconStyle(color=color, scale=0.7, icon=simplekml.Icon(
            href=self.get_subject_icon(subject)))
        sn_style.labelstyle = simplekml.LabelStyle(scale=0)
        sn_style.balloonstyle = simplekml.BalloonStyle(
            bgcolor=color, text='$[description')
        document.styles.append(sn_style)

        style_map = simplekml.StyleMap()
        style_map._id = 'msn_{0}_Finalmarkerstyle'.format(
            subject.name.replace(' ', '_'))
        style_map.normalstyle = sn_style
        style_map.highlightstyle = sh_style
        document.stylemaps.append(style_map)

        point = document.newpoint()
        point.coords = [(last_obs['location'].x, last_obs['location'].y)]
        point.timestamp.when = timestamp
        point.placemark.name = 'Last Position: {0}'.format(timestamp)
        point.placemark.snippet = simplekml.Snippet('')
        point.placemark.description = timestamp
        point.stylemap = style_map

    def add_overlay_to_folder(self, folder):
        overlay = folder.newscreenoverlay()
        overlay.overlayxy = simplekml.OverlayXY(x=0, y=0,
                                                xunits=simplekml.Units.fraction,
                                                yunits=simplekml.Units.fraction)
        overlay.screenxy = simplekml.ScreenXY(x=0, y=0,
                                              xunits=simplekml.Units.fraction,
                                              yunits=simplekml.Units.fraction)
        overlay.rotationxy = simplekml.RotationXY(x=0, y=0,
                                                  xunits=simplekml.Units.fraction,
                                                  yunits=simplekml.Units.fraction)
        overlay.size = simplekml.Size(x=0, y=0,
                                      xunits=simplekml.Units.fraction,
                                      yunits=simplekml.Units.fraction)
        overlay.name = 'Logo'

        # TODO: Serve our own image.
        overlay.icon.href = 'http://107.21.94.89/Images/Logos/STE_Logo.png'

    def get(self, request, *args, **kwargs):
        subject = generics.get_object_or_404(
            models.Subject.objects.all(), pk=self.kwargs['id'])
        self.check_object_permissions(self.request, subject)
        k = simplekml.Kml()
        k.document = simplekml.Folder(name=subject.name)
        k.document._id = None
        k.document.visibility = 1
        self.add_overlay_to_folder(k.document)

        observations = list(self.get_allowed_subject_observations(subject))

        if len(observations) > 0:
            self.add_points_document(k.document, subject, observations)
            self.add_tracks_document(k.document, subject, observations)
            self.add_position_document(k.document, subject, observations)
        filename = 'TrackingData{}'.format(
            datetime.datetime.utcnow().strftime('%Y%M%d%H%M'))
        kml_str = k.kml(format=False)
        return render_to_kmz(kml_str, filename)
