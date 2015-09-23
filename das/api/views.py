import logging
import datetime

import simplejson as json
import dateutil.parser
import pytz
from django.http import Http404
from rest_framework import generics
from rest_framework.views import APIView, exception_handler
from rest_framework.response import Response
from rest_framework.metadata import SimpleMetadata
from rest_framework.permissions import AllowAny
from oauth2_provider.views import ProtectedResourceView

from observations.models import Subject, Observation, SubjectSource, Source
from das_server import utils
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


def api_exception_handler(exc, context):
    """
    Our custom error, that returns payload as JSON
    """
    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data.pop('detail', None)
        status = {'code': response.status_code,
                  'message': response.status_text,
                  }
        if detail:
            status['detail'] = detail
        response.data['status'] = status
    return response


class StatusView(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = serializers.VersionSerializer

    def get_object(self):
        return {'version': 'v1.0'} #request.version}


class SubjectsView(generics.ListAPIView):
    queryset = Subject.objects.all()
    serializer_class = serializers.SubjectSerializer


class SubjectView(generics.RetrieveAPIView):
    serializer_class = serializers.SubjectSerializer
    queryset = Subject.objects.all()

    def get_serializer_context(self):
        context = {}
        subject = self.get_object()
        last_position = Observation.objects.get_last_observation(subject)
        if last_position:
            first_position = Observation.objects.get_first_observation(subject)
            context = dict(first_position=first_position,
                           last_position=last_position,
                           request=self.request,
                           tracks_available=True)
        else:
            context['tracks_available'] = False
        return context


class SubjectBaseView(generics.RetrieveAPIView):
    subject_id = None
    _subject = None

    @staticmethod
    def filter_result(subject, detail_type='list'):
        result = {k: getattr(subject, k) for k in SubjectBaseView.fields if hasattr(subject, k)}
        additional = subject.additional
        result.update({k: additional[k] for k in SubjectBaseView.fields if k in additional})

        if detail_type == 'detail':
            last_position = Observation.objects.get_last_observation(subject)
            result['tracks_available'] = bool(last_position)
            if last_position:
                first_position = Observation.objects.get_first_observation(subject)
                result['last_position'] = make_feature(last_position.location, subject,
                                                       time=last_position.recorded_at)
                result['tracks_range'] = (first_position.recorded_at,
                                          last_position.recorded_at)
        return result

    @property
    def subject(self):
        if not self._subject:
            _subject = Subject.objects.get(id=self.subject_id)
        return _subject


class SubjectSourcesView(generics.ListAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(Subject.objects.all(), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, subject)

        self.subject_sources = SubjectSource.objects.get_subject_sources(subject)
        sources = Source.objects.filter(pk__in=self.subject_sources.values('source'))
        return sources


class SubjectSourceView(generics.RetrieveAPIView):
    serializer_class = serializers.SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(Subject.objects.all(), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, subject)

        self.subject_sources = SubjectSource.objects.get_subject_sources(subject)
        sources = Source.objects.all()
        return sources

    def get_object(self):
        queryset = self.get_queryset()
        filters = {'id': self.kwargs['source_id']}

        obj = generics.get_object_or_404(queryset, **filters)
        self.check_object_permissions(self.request, obj)
        return obj


class SubjectSourceTrackView(generics.RetrieveAPIView):
    serializer_class = serializers.TrackSerializer
    queryset = Subject.objects.all()

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

        sds = SubjectSource.objects.get_subject_source(subject, source_id)
        if not sds:
            raise Http404

        if since or until:
            observations = Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        context['times'] = times
        context['coordinates'] = coordinates
        return context


class SubjectTracksView(generics.RetrieveAPIView):
    serializer_class = serializers.TrackSerializer
    queryset = Subject.objects.all()

    def get_serializer_context(self):
        context = {}
        subject = self.get_object()
        since = self.request.query_params.get('since', None)
        if isinstance(since, str):
            since = dateparse(since)

        until = self.request.query_params.get('until', None)
        if until:
            until = dateparse(until)

        sds = SubjectSource.objects.filter(subject=subject)
        if not sds:
            raise Http404

        if since or until:
            observations = Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        context['times'] = times
        context['coordinates'] = coordinates
        return context