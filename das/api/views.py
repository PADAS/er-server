import logging

import simplejson
from django.views.generic import View, CreateView
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from sensors.models import Subject, Observation
import djgeojson
logger = logging.getLogger(__name__)


def empty_geojson_featurecollection():
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": []
        }


def empty_geojson_feature():
    return {
        "type": "Feature",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "geometry": {}
        }


class SubjectTrackGeoJsonView(View):
    def get(self, request):
        subject_id = self.request.GET['subject_id']
        subject = Subject.objects.filert(subject_id=subject_id)
        color = subject.extra.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))

        result = empty_geojson_featurecollection()
        points = Observation.objects.filter()
        for point in points:
            coordinates = []
            times = []

        feature = {
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "type": "Feature",
            "properties": {
                "name": subject.name,
            },

        }
        if color:
            feature['style'] = {
                "color": color,
                "iconUrl": "http://107.21.94.89/Images/AnimalIcons/Elephant_Male.png",
                "opacity": 1
            }
        #see https://github.com/mapbox/geojson-coordinate-properties
        feature['properties']['coordinateProperties'] = {'times': times}

        result['features'].append(feature)
        return HttpResponse(simplejson.dumps(result), content_type='application/json')
