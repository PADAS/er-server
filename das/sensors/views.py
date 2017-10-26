import logging

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response

from utils.drf import AllowAnyGet
from sensors.handlers import GsatHandler, GenericSensorHandler,\
    DasRadioAgentHandler
from sensors.camera_trap import CameraTrapSensorHandler
from observations.serializers import ObservationSerializer


class SensorObservation(generics.GenericAPIView):

    permission_classes = (AllowAnyGet, )
    serializer_class = ObservationSerializer

    def get(self, request, *args, sensor_type=None, provider_name=None, **kwargs):

        if sensor_type == GsatHandler.SENSOR_TYPE:
            return GsatHandler().handle_observation(request, provider_name)

        # TODO: Write a validator to do this error response.
        errordata = {
            'data':
                {'sensor_type': _(
                    '{} is not a valid sensor_type').format(sensor_type)}
        }

        return Response(data=errordata, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, *args, sensor_type=None, provider_name=None, **kwargs):
        if sensor_type == DasRadioAgentHandler.SENSOR_TYPE:
            return DasRadioAgentHandler().handle_observation(request, provider_name)

        if sensor_type == CameraTrapSensorHandler.SENSOR_TYPE:
            return CameraTrapSensorHandler.post(request, provider_name)

        return GenericSensorHandler().handle_observation(request, sensor_type=sensor_type, provider_name=provider_name)
