import logging

import simplejson
from django.views.generic import View, CreateView
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import djgeojson

from sensors.models import Subject, Observation, SubjectDevice
from .serializers import SubjectSerializer, ObservationSerializer
import utils

logger = logging.getLogger(__name__)


class AnimalsView(APIView):
    def get(self, request, format=None):
        animals = Subject.objects.all()
        serializer = SubjectSerializer(animals, many=True)
        return Response(serializer.data)

class AnimalTrackView(APIView):
    def get_notright(self, request, id, format=None):
        sds = SubjectDevice.objects.filter(subject_id=id)
        if not sds:
            raise Http404

        observations = Observation.objects.get_device_range_observations(sds)
        serializer = ObservationSerializer(observations, many=True)
        return Response(serializer.data)

    def get(self, request, id, format=None):
        try:
            subject = Subject.objects.get(id=id)
        except Subject.DoesNotExist:
            return Http404

        color = subject.additional.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))

        sds = SubjectDevice.objects.filter(subject_id=id)
        if not sds:
            raise Http404
        observations = Observation.objects.get_device_range_observations(sds)
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

        result = utils.empty_geojson_featurecollection()
        result['features'].append(feature)
        return HttpResponse(utils.json_string(result), content_type='application/json')


class SubjectTrackGeoJsonView(View):
    def get(self, request):
        subject_id = self.request.GET['subject_id']
        subject = Subject.objects.filert(subject_id=subject_id)
        color = subject.additional.get('rgb', None)
        if color:
            color = "#" + "".join(color.split(','))

        result = utils.empty_geojson_featurecollection()
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
        return HttpResponse(utils.json_string(result), content_type='application/json')
