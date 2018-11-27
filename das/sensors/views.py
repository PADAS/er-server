import logging

from django.utils.translation import ugettext_lazy as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser, FileUploadParser
from utils.json import JSONTextParser

from utils.drf import AllowAnyGet
from sensors.handlers import GsatHandler, GenericSensorHandler,\
    DasRadioAgentHandler, SkylineVehicleTrackerHandler, FollowltTrackerHandler
from sensors.camera_trap import CameraTrapSensorHandler
from observations.serializers import ObservationSerializer


class SensorObservation(generics.GenericAPIView):

    permission_classes = (AllowAnyGet,)
    serializer_class = ObservationSerializer
    parser_classes = (JSONParser, JSONTextParser, MultiPartParser, FormParser, FileUploadParser)

    def get(self, request, *args, sensor_type=None, provider_key=None, **kwargs):

        if sensor_type == GsatHandler.SENSOR_TYPE:
            return GsatHandler.post(request, provider_key)

        # TODO: Write a validator to do this error response.
        errordata = {
            'data':
                {'sensor_type': _(
                    '{} is not a valid sensor_type').format(sensor_type)}
        }

        return Response(data=errordata, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, *args, sensor_type=None, provider_key=None, **kwargs):
        if sensor_type == DasRadioAgentHandler.SENSOR_TYPE:
            return DasRadioAgentHandler.post(request, provider_key)

        if sensor_type == CameraTrapSensorHandler.SENSOR_TYPE:
            return CameraTrapSensorHandler.post(request, provider_key)

        if sensor_type == SkylineVehicleTrackerHandler.SENSOR_TYPE:
            return SkylineVehicleTrackerHandler.post(request, sensor_type=sensor_type, provider_key=provider_key)

        if sensor_type == FollowltTrackerHandler.SENSOR_TYPE:
            return FollowltTrackerHandler.post(request, sensor_type=sensor_type,
                                               provider_key=provider_key)
        return GenericSensorHandler.post(request, sensor_type=sensor_type, provider_key=provider_key)
