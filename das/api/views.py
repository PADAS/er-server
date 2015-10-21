import logging
import datetime

import simplejson as json
import dateutil.parser
import pytz
from django.utils.translation import ugettext_lazy as _
from django.http import Http404, JsonResponse
from django.contrib.auth import get_user_model

import django.views.defaults
from rest_framework import generics
from rest_framework.views import exception_handler
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.compat import set_rollback
import rest_framework.status

from observations import models
import api.serializers as serializers


logger = logging.getLogger(__name__)

LAST_DAYS = datetime.timedelta(days=16)


def default_since():
    """default value for since
    last 30 days is the default
    """
    return datetime.datetime.now(pytz.utc) - datetime.timedelta(days=30)


def dateparse(date_str, default_tz=pytz.utc):
    dt = dateutil.parser.parse(date_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def fixup_api_response(response):
    """The DAS api returns a json error payload"""
    if response:
        detail = response.data.pop('detail', None)
        status = {'code': response.status_code,
                  'message': response.status_text,
                  }
        if detail:
            status['detail'] = detail
        response.data['status'] = status
    return response


def api_exception_handler(exc, context):
    """
    Our custom error handler, that returns payload as JSON
    """
    response = exception_handler(exc, context)
    if not response:
        message = str(_('Internal Server Error'))
        detail = str(exc)
        data = {'detail': detail} if detail else {}
        set_rollback()
        response = Response(data,
                            status=rest_framework.status.HTTP_500_INTERNAL_SERVER_ERROR)
    return fixup_api_response(response)


def error404View(request, template_name='404.html'):
    """Handle 404 in our api"""
    if not request.path.startswith('/api/v1.0/'):
        return django.views.defaults.page_not_found(request, template_name=template_name)
    response = Response({},
                        status=rest_framework.status.HTTP_404_NOT_FOUND,
                        )
    fixup_api_response(response)
    response = JsonResponse(data=response.data)
    return response


class StatusView(generics.RetrieveAPIView):
    """
    What is the server status and current api version.
    ---

    """
    permission_classes = (AllowAny,)
    serializer_class = serializers.VersionSerializer

    def get_object(self):
        return {'version': 'v1.0'} #request.version}


class UsersView(generics.ListAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer


class UserView(generics.RetrieveAPIView):
    lookup_field = 'id'
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'me':
            self.kwargs[lookup_url_kwarg] = self.request.user.id
        return super(UserView, self).get_object()


class RegionsView(generics.ListAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class RegionView(generics.RetrieveAPIView):
    lookup_field = 'slug'
    queryset = models.Region.objects.all()
    serializer_class = serializers.RegionSerializer


class SubjectsView(generics.ListAPIView):
    queryset = models.Subject.objects.all()
    serializer_class = serializers.SubjectSerializer


class RegionSubjectsView(generics.ListAPIView):
    lookup_field = 'slug'
    serializer_class = serializers.SubjectSerializer
    def get_queryset(self):
        region = generics.get_object_or_404(models.Region.objects.all(),
                                            slug=self.kwargs['slug'])
        self.check_object_permissions(self.request, region)
        subjects = models.Subject.objects.by_region(region)
        return subjects

    def get_serializer_context(self):
        context = {'request': self.request}
        context['show_last_position_date'] = True
        return context


class SubjectView(generics.RetrieveAPIView):
    serializer_class = serializers.SubjectSerializer
    queryset = models.Subject.objects.all()
    lookup_field = 'id'

    def get_serializer_context(self):
        context = {'request': self.request}
        subject = self.get_object()
        last_position = models.Observation.objects.get_last_observation(subject)
        if last_position:
            first_position = models.Observation.objects.get_first_observation(subject)
            context = dict(first_position=first_position,
                           last_position=last_position,
                           request=self.request,
                           tracks_available=True,)
        else:
            context['tracks_available'] = False
        return context


class SubjectSourcesView(generics.ListAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(models.Subject.objects.all(), pk=self.kwargs['id'])
        self.check_object_permissions(self.request, subject)

        self.subject_sources = models.SubjectSource.objects.get_subject_sources(subject)
        sources = models.Source.objects.filter(pk__in=self.subject_sources.values('source'))
        return sources


class SubjectSourceView(generics.RetrieveAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(models.Subject.objects.all(), pk=self.kwargs['id'])
        self.check_object_permissions(self.request, subject)

        self.subject_sources = models.SubjectSource.objects.get_subject_sources(subject)
        sources = models.Source.objects.all()
        return sources

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

    def get_serializer_context(self):
        context = {}
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

        if since or until:
            observations = models.Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = models.Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        context['times'] = times
        context['coordinates'] = coordinates
        context['request'] = self.request
        return context


class SubjectTracksView(generics.RetrieveAPIView):
    lookup_field = 'id'
    serializer_class = serializers.TrackSerializer
    queryset = models.Subject.objects.all()

    def get_serializer_context(self):
        context = {}
        subject = self.get_object()
        since = self.request.query_params.get('since', None)
        if isinstance(since, str):
            since = dateparse(since)

        until = self.request.query_params.get('until', None)
        if until:
            until = dateparse(until)

        sds = models.SubjectSource.objects.filter(subject=subject)
        if not sds:
            raise Http404

        if since or until:
            observations = models.Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = models.Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        context['times'] = times
        context['coordinates'] = coordinates
        context['request'] = self.request
        return context


class ObservationView(generics.mixins.CreateModelMixin,
                      generics.RetrieveAPIView):
    lookup_field = 'id'
    queryset = models.Observation.objects.all()
    serializer_class = serializers.ObservationSerializer
