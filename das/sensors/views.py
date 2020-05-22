from rest_framework import generics
from rest_framework.parsers import (FileUploadParser, FormParser, JSONParser,
                                    MultiPartParser)

from observations.serializers import ObservationSerializer
from sensors.camera_trap import CameraTrapSensorHandler
from sensors.capturs import CaptursPushHandler
from sensors.handlers import (DasRadioAgentHandler, EzyTrackHandler,
                              FollowltTrackerHandler, GateHandler,
                              GenericSensorHandler, GFWAlertHandler,
                              GsatHandler, SigFoxPushHandler,
                              SkylineVehicleTrackerHandler, TestHandler,
                              TractVehicleHandler)
from sensors.sigfox_foundation_push_handler import SigfoxFoundationPushHandler
from utils.drf import AllowAnyGet
from utils.json import JSONTextParser
from utils.stats import increment


class BaseSensorsView(generics.GenericAPIView):
    permission_classes = (AllowAnyGet,)
    serializer_class = ObservationSerializer
    parser_classes = (JSONParser, JSONTextParser,
                      MultiPartParser, FormParser, FileUploadParser)


class GenericSensorHandlerView(BaseSensorsView):
    serializer_class = GenericSensorHandler.serializer_class

    def post(self, request, *args, sensor_type=None, provider_key=None, **kwargs):

        increment(f'sensor_{sensor_type}')
        increment(f'sensor_{sensor_type}_{provider_key}')
        return GenericSensorHandler.post(request, sensor_type=sensor_type, provider_key=provider_key)


class GsatHandlerView(BaseSensorsView):
    # Identify appropriate serializers
    def get(self, request, provider_key=None):
        return GsatHandler.post(request, provider_key)


class RadioAgentHandlerView(BaseSensorsView):
    serializer_class = DasRadioAgentHandler.serializer_class

    def post(self, request, provider_key=None):
        return DasRadioAgentHandler.post(request, provider_key)


class CameraTrapHandlerView(BaseSensorsView):
    serializer_class = CameraTrapSensorHandler.serializer_class

    def post(self, request, provider_key=None):
        return CameraTrapSensorHandler.post(request, provider_key)


class SkylineVehicleHandlerView(BaseSensorsView):
    serializer_class = SkylineVehicleTrackerHandler.serializer_class

    def post(self, request, provider_key=None):
        return SkylineVehicleTrackerHandler.post(request, provider_key)


class TractVehicleHandlerView(BaseSensorsView):
    serializer_class = TractVehicleHandler.serializer_class

    def post(self, request, provider_key=None):
        return TractVehicleHandler.post(request, provider_key)


class FollowltHandlerView(BaseSensorsView):
    serializer_class = FollowltTrackerHandler.serializer_class

    def post(self, request, provider_key=None):
        return FollowltTrackerHandler.post(request, provider_key)


class SigFoxHandlerView(BaseSensorsView):
    serializer_class = SigFoxPushHandler.serializer_class

    def post(self, request, provider_key=None):
        return SigFoxPushHandler.post(request, provider_key)


class GFWAlertHandlerView(BaseSensorsView):
    serializer_class = GFWAlertHandler.serializer_class

    def post(self, request, provider_key=None):
        return GFWAlertHandler.post(request, provider_key=provider_key)


class SigfoxFoundationHandlerView(BaseSensorsView):
    serializer_class = SigfoxFoundationPushHandler.serializer_class

    def post(self, request, provider_key=None):
        return SigfoxFoundationPushHandler.post(request, provider_key)


class GateHandlerView(BaseSensorsView):
    def post(self, request, provider_key=None):
        return GateHandler.post(request, provider_key)


class TestHandlerView(BaseSensorsView):
    def post(self, request, provider_key=None):
        return TestHandler.post(request, provider_key)


class CaptursHandlerView(BaseSensorsView):
    serializer_class = CaptursPushHandler.serializer_class

    def post(self, request, provider_key=None):
        return CaptursPushHandler.post(request, provider_key)


class EzyTrackHandlerView(BaseSensorsView):
    serializer_class = EzyTrackHandler.serializer_class

    def post(self, request, provider_key=None):
        return EzyTrackHandler.post(request, provider_key)
