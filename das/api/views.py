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
    def get_object(self, id):
        try:
            return SubjectDevice.objects.get(id=id)
        except SubjectDevice.DoesNotExist:
            raise Http404

    def get(self, request, id, format=None):
        subjectdevice = self.get_object(id)
        serializer = ObservationSerializer(subjectdevice)
        return Response(serializer.data)



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
        return HttpResponse(simplejson.dumps(result), content_type='application/json')
