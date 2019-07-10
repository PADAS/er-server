import logging

from django.utils.translation import ugettext_lazy as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser, FileUploadParser
from utils.json import JSONTextParser

from utils.drf import AllowAnyGet
from sensors.handlers import GsatHandler, GenericSensorHandler,\
    DasRadioAgentHandler, SkylineVehicleTrackerHandler, FollowltTrackerHandler,  TractVehicleHandler, SigFoxPushHandler
from sensors.camera_trap import CameraTrapSensorHandler
from sensors.gfw_alert_handler import GFWAlertHandler
from observations.serializers import ObservationSerializer

from utils.stats import increment


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

        increment(f'sensor_{sensor_type}')
        increment(f'sensor_{sensor_type}_{provider_key}')

        if sensor_type == DasRadioAgentHandler.SENSOR_TYPE:
            return DasRadioAgentHandler.post(request, provider_key)

        elif sensor_type == CameraTrapSensorHandler.SENSOR_TYPE:
            return CameraTrapSensorHandler.post(request, provider_key)

        elif sensor_type == SkylineVehicleTrackerHandler.SENSOR_TYPE:
            return SkylineVehicleTrackerHandler.post(request, sensor_type=sensor_type, 
                                                        provider_key=provider_key)

        elif sensor_type == TractVehicleHandler.SENSOR_TYPE:
            return TractVehicleHandler.post(request, sensor_type=sensor_type, 
                                                provider_key=provider_key)

        elif sensor_type == FollowltTrackerHandler.SENSOR_TYPE:
            return FollowltTrackerHandler.post(request, sensor_type=sensor_type,
                                               provider_key=provider_key)

        elif sensor_type == SigFoxPushHandler.SENSOR_TYPE:
            return SigFoxPushHandler.post(request, sensor_type=sensor_type,
                                               provider_key=provider_key)

        elif sensor_type == GFWAlertHandler.SENSOR_TYPE:
            return GFWAlertHandler.post(request, subscription_id=provider_key)
        else:
            return GenericSensorHandler.post(request, sensor_type=sensor_type, 
                                                provider_key=provider_key)
