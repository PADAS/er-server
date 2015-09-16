import logging
import datetime
import simplejson as json
from django.views.generic import View
from django.http import HttpResponse
import dateutil.parser
import pytz
from observations.models import Subject, Observation, SubjectSource, Source
from das_server import utils
from django.contrib.gis.geos import Point

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


class StatusView(View):
    def get(self, request):
        result = {'version': '1.0'}
        return ApiJsonResponse(result)

class SourceBaseView(View):
    fields = ('id', 'source_type', 'manufacturer_id', 'model_name')

    @staticmethod
    def filter_result(source):
        result = {k: getattr(source, k) for k in SourceBaseView.fields if hasattr(source, k)}
        result.update(source.additional)
        return result


class SubjectBaseView(View):
    fields = ('id', 'name', 'region', 'country', 'subject_type', 'sex', 'species')
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
            result.append(SubjectBaseView.filter_result(subject, detail_type='list'))
        return ApiJsonResponse(result)


class SubjectView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id
        result = self.filter_result(self.subject, detail_type='detail')
        return ApiJsonResponse(result)


class SubjectSourcesView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id

        result = []
        s_sources = SubjectSource.objects.get_subject_sources(self.subject)
        for subject_source in s_sources:
            source = Source.objects.get(id=subject_source.source_id)
            source = SourceBaseView.filter_result(source)
            source['assigned_range'] = subject_source.assigned_range
            result.append(source)

        return ApiJsonResponse(result)


class SubjectSourceTrackView(SubjectBaseView):
    def get(self, request, subject_id, source_id):
        self.subject_id = subject_id

        since = request.GET.get('since', None)
        if isinstance(since, str):
            since = dateparse(since)

        until = request.GET.get('until', None)
        if until:
            until = dateparse(until)

        color = self.subject.color

        sds = SubjectSource.objects.get_subject_source(self.subject, source_id)
        if not sds:
            return ApiError(404)

        if since or until:
            observations = Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        feature = make_feature(coordinates, self.subject, times)

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)
        return ApiJsonResponse(result)


def make_feature(coordinates, subject, coordinate_times=None, time=None):
    is_point = isinstance(coordinates, Point)
    feature = {
        'geometry': {
            'type': 'LineString' if not is_point else 'Point',
            'coordinates': coordinates if not is_point else coordinates.tuple
        },
        'type': 'Feature',
        'properties': {
            'title': subject.name,
        },
    }
    properties = feature['properties']
    if hasattr(subject, 'color'):
        feature['style'] = {
            "color": subject.color,
            "iconUrl": subject.image_url,
            "opacity": 1,
            "deprecating": "use https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0"
        }
        #see https://github.com/mapbox/simplestyle-spec/tree/master/1.1.0
        properties['stroke'] = subject.color
        properties['stroke-opacity'] = 1.0
        properties['stroke-width'] = 2
        properties['image'] = subject.image_url

    #see https://github.com/mapbox/geojson-coordinate-properties
    if coordinate_times:
        properties['coordinateProperties'] = {'times': coordinate_times}
    if time:
        properties['DateTime'] = time
    return feature


class SubjectTracksView(SubjectBaseView):
    def get(self, request, subject_id):
        self.subject_id = subject_id

        since = request.GET.get('since', None)
        if isinstance(since, str):
            since = dateparse(since)

        until = request.GET.get('until', None)
        if until:
            until = dateparse(until)

        sds = SubjectSource.objects.filter(subject_id=subject_id)
        if not sds:
            return ApiError(404)

        if since or until:
            observations = Observation.objects.get_source_range_observations(sds, since, until)
        else:
            observations = Observation.objects.get_source_range_observations_last(sds, LAST_DAYS)

        coordinates = []
        times = []
        for ob in observations:
            coordinates.append(ob.location.coords)
            times.append(ob.recorded_at)

        feature = make_feature(coordinates, self.subject, times)

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)

        return ApiJsonResponse(result)
