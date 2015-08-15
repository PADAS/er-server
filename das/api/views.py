import logging
import datetime
import simplejson as json
from django.views.generic import View
from django.http import HttpResponse
import dateutil.parser
import pytz
from observations.models import Subject, Observation, SubjectSource, Source
from das_server import utils

logger = logging.getLogger(__name__)


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


class ApiJsonResponse(HttpResponse):
    """
    Custom data payload for the API
    returns error, data
    """

    def __init__(self, data, encoder=utils.ExtendedJSONEncoder, **kwargs):
        kwargs.setdefault('content_type', 'application/json')
        result = {'data': data, 'status': {'code': 200, 'message': 'OK'}}
        result = json.dumps(result, cls=encoder)
        super(ApiJsonResponse, self).__init__(content=result, **kwargs)


class ApiError(HttpResponse):
    """
    Our custom error, that returns payload as JSON
    """

    def __init__(self, status_code, encoder=utils.ExtendedJSONEncoder, **kwargs):
        kwargs.setdefault('content_type', 'application/json')
        self.status_code = status_code
        super(ApiError, self).__init__(**kwargs)
        result = {'status': {'code': self.status_code, 'message': self.reason_phrase}}
        self.content = json.dumps(result, cls=encoder)


class SourceBaseView(View):
    fields = ('id', 'source_type', 'manufacturer_id', 'model_name', 'additional',)


class SubjectBaseView(View):
    fields = ('id', 'name')
    subject_id = None
    _subject = None

    @property
    def subject(self):
        if not self._subject:
            try:
                _subject = Subject.objects.get(id=self.subject_id)
            except Subject.DoesNotExist:
                return ApiError(404)
        return _subject


class SubjectsView(View):
    def get(self, request):
        subjects = Subject.objects.all()
        result = []
        for subject in subjects:
            result.append({k: getattr(subject, k) for k in SubjectBaseView.fields})
        return ApiJsonResponse(result)


class SubjectView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id
        result = {k: getattr(self.subject, k) for k in self.fields}
        return ApiJsonResponse(result)


class SubjectSourcesView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id

        result = []
        s_sources = SubjectSource.objects.get_subject_sources(self.subject)
        for subject_source in s_sources:
            source = Source.objects.get(id=subject_source.source_id)
            source = {k: getattr(source, k) for k in SourceBaseView.fields}
            source['assigned_range'] = subject_source.assigned_range
            result.append(source)

        return ApiJsonResponse(result)


class SubjectSourceTrackView(SubjectBaseView):
    def get(self, request, subject_id, source_id):
        self.subject_id = subject_id

        since = request.GET.get('since', default_since())
        if isinstance(since, str):
            since = dateparse(since)

        until = request.GET.get('until', None)
        if until:
            until = dateparse(until)

        color = self.subject.additional.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))

        sds = SubjectSource.objects.get_subject_source(self.subject, source_id)
        if not sds:
            return ApiError(404)
        observations = Observation.objects.get_source_range_observations(sds, since, until)
        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        feature = {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "type": "Feature",
            "properties": {
                "name": self.subject.name,
            },

        }
        if color:
            feature['style'] = {
                "color": self.subject.color,
                "iconUrl": self.subject.image_url,
                "opacity": 1
            }
        #see https://github.com/mapbox/geojson-coordinate-properties
        feature['properties']['coordinateProperties'] = {'times': times}

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)
        return ApiJsonResponse(result)


class SubjectTracksView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id

        since = request.GET.get('since', default_since())
        if isinstance(since, str):
            since = dateparse(since)

        until = request.GET.get('until', None)
        if until:
            until = dateparse(until)

        sds = SubjectSource.objects.filter(subject_id=subject_id)
        if not sds:
            return ApiError(404)
        observations = Observation.objects.get_source_range_observations(sds, since, until)
        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        feature = {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "type": "Feature",
            "properties": {
                "name": self.subject.name,
            },

        }

        if hasattr(self.subject, 'color'):
            feature['style'] = {
                "color": self.subject.color,
                "iconUrl": self.subject.image_url,
                "opacity": 1
            }
        #see https://github.com/mapbox/geojson-coordinate-properties
        feature['properties']['coordinateProperties'] = {'times': times}

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)

        return ApiJsonResponse(result)
