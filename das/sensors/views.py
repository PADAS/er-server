from django.conf import settings
from rest_framework import generics
from rest_framework.parsers import (FileUploadParser, FormParser, JSONParser,
                                    MultiPartParser)
from rest_framework.schemas.openapi import AutoSchema

from observations.serializers import ObservationSerializer
from sensors.camera_trap import CameraTrapSensorHandler
from sensors.capturs import CaptursPushHandler
from sensors.handlers import (DasRadioAgentHandler, EzyTrackHandler,
                              FollowltTrackerHandler, GateHandler,
                              GenericSensorHandler, GFWAlertHandler,
                              GsatHandler, InreachPushHandler,
                              SigFoxPushHandler, SkylineVehicleTrackerHandler,
                              TestHandler, TractVehicleHandler)
from sensors.sigfox_foundation_push_handler import SigfoxFoundationPushHandler
from utils.drf import AllowAnyGet
from utils.json import JSONTextParser
from utils.stats import increment

schema_class = settings.REST_FRAMEWORK.get('DEFAULT_SCHEMA_CLASS', '')


class CustomSchema(AutoSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        operation['tags'] = ["Sensors"]
        operation['summary'] = getattr(self.view, method.lower()).__doc__

        return operation

    def _map_serializer(self, serializer):
        result = super()._map_serializer(serializer)
        for res in result.get('properties').values():
            default = res.get('default')
            if default:
                res['default'] = [] if default == type([]) else {} if default == type({}) else default
        return result


class BaseSensorsView(generics.GenericAPIView):
    permission_classes = (AllowAnyGet,)
    serializer_class = ObservationSerializer
    parser_classes = (JSONParser, JSONTextParser,
                      MultiPartParser, FormParser, FileUploadParser)

    if 'coreapi' not in schema_class:
        schema = CustomSchema()


class GenericSensorHandlerView(BaseSensorsView):
    serializer_class = GenericSensorHandler.serializer_class

    def post(self, request, *args, sensor_type=None, provider_key=None, **kwargs):
        """ Add Generic Sensor Observations """

        increment(f'sensor_{sensor_type}')
        increment(f'sensor_{sensor_type}_{provider_key}')
        return GenericSensorHandler.post(request, sensor_type=sensor_type, provider_key=provider_key)


class GsatHandlerView(BaseSensorsView):
    # Identify appropriate serializers
    def get(self, request, provider_key=None):
        """ Add Gsat Observations """
        return GsatHandler.post(request, provider_key)


class RadioAgentHandlerView(BaseSensorsView):
    serializer_class = DasRadioAgentHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add RadioAgent Observations """
        return DasRadioAgentHandler.post(request, provider_key)


class CameraTrapHandlerView(BaseSensorsView):
    serializer_class = CameraTrapSensorHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add CameraTrap Observations """
        return CameraTrapSensorHandler.post(request, provider_key)


class SkylineVehicleHandlerView(BaseSensorsView):
    serializer_class = SkylineVehicleTrackerHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Skyline Vehicle Tracker Observations """
        return SkylineVehicleTrackerHandler.post(request, provider_key)


class TractVehicleHandlerView(BaseSensorsView):
    serializer_class = TractVehicleHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Tract Vehicle Observations """
        return TractVehicleHandler.post(request, provider_key)


class FollowltHandlerView(BaseSensorsView):
    serializer_class = FollowltTrackerHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Followlt Tracker Observations """
        return FollowltTrackerHandler.post(request, provider_key)


class SigFoxHandlerView(BaseSensorsView):
    serializer_class = SigFoxPushHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add SigFox Observations """
        return SigFoxPushHandler.post(request, provider_key)


class GFWAlertHandlerView(BaseSensorsView):
    serializer_class = GFWAlertHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add GFW Alert Observations """
        return GFWAlertHandler.post(request, provider_key=provider_key)


class SigfoxFoundationHandlerView(BaseSensorsView):
    serializer_class = SigfoxFoundationPushHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Sigfox Foundation Observations """
        return SigfoxFoundationPushHandler.post(request, provider_key)


class GateHandlerView(BaseSensorsView):
    def post(self, request, provider_key=None):
        """ Add Gate Sensor Observations """
        return GateHandler.post(request, provider_key)


class TestHandlerView(BaseSensorsView):
    def post(self, request, provider_key=None):
        """ Add Test Sensor Observations """
        return TestHandler.post(request, provider_key)


class CaptursHandlerView(BaseSensorsView):
    serializer_class = CaptursPushHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Capturs Observations """
        return CaptursPushHandler.post(request, provider_key)


class EzyTrackHandlerView(BaseSensorsView):
    serializer_class = EzyTrackHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Ezy Track Observations """
        return EzyTrackHandler.post(request, provider_key)


class InreachHandlerView(BaseSensorsView):
    serializer_class = InreachPushHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Inreach Track Observations """
        return InreachPushHandler.post(request, provider_key)
