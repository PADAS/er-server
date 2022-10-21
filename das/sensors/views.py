from rest_framework import generics
from rest_framework.parsers import (FileUploadParser, FormParser, JSONParser,
                                    MultiPartParser)
from rest_framework.permissions import AllowAny

from das_server.views import CustomSchema
from observations.serializers import ObservationSerializer
from sensors.camera_trap import CameraTrapSensorHandler
from sensors.capturs import CaptursPushHandler
from sensors.handlers import (DasRadioAgentHandler, ErTrackHandler,
                              EzyTrackHandler, FollowltTrackerHandler,
                              GateHandler, GenericSensorHandler,
                              GFWAlertHandler, GsatHandler, InreachPushHandler,
                              SigFoxPushHandler, SkylineVehicleTrackerHandler,
                              TestHandler, TractVehicleHandler)
from sensors.kerlink_push_handler import KerlinkHandler
from sensors.sigfox_foundation_push_handler import (SigfoxV1Handler,
                                                    SigfoxV2Handler)
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
        """ Add Generic Sensor Observations """

        increment("sensor", tags={
                  "type": sensor_type, "provider": provider_key})
        return GenericSensorHandler.post(request, provider_key=provider_key, sensor_type=sensor_type)


class ERTrackHandlerView(BaseSensorsView):
    serializer_class = GenericSensorHandler.serializer_class

    def post(self, request, provider_key=None):
        """ Add ER Track Observations """
        return ErTrackHandler.post(request, provider_key=provider_key)


class GsatSchema(CustomSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if method == 'GET':
            query_params = [
                {'name': 'uniqueid', 'in': 'query', 'required': True},
                {'name': 'lat', 'in': 'query', 'required': True,
                    'description': 'latitude'},
                {'name': 'lng', 'in': 'query', 'required': True,
                    'description': 'longitude'},
                {'name': 'time', 'in': 'query', 'required': True,
                    'description': 'recorded time'},
                {'name': 'alt', 'in': 'query', 'description': 'altitude'},
                {'name': 'heading', 'in': 'query',
                    'description': 'Direction subject is headed'},
                {'name': 'speed', 'in': 'query', 'description': 'subject speed'},
                {'name': 'emer', 'in': 'query', 'description': 'If emergency',
                    'schema': {'type': 'bool'}},
            ]
            operation['parameters'].extend(query_params)
        return operation


class GsatHandlerView(BaseSensorsView):
    serializer_class = None
    schema = GsatSchema()

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
    serializer_class = SigfoxV1Handler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Sigfox Foundation Observations """
        return SigfoxV1Handler.post(request, provider_key)


class SigfoxV2FoundationHandlerView(BaseSensorsView):
    serializer_class = SigfoxV2Handler.serializer_class

    def post(self, request, provider_key=None):
        """ Add Sigfox V2 Foundation Observations """
        return SigfoxV2Handler.post(request, provider_key)


class GateHandlerView(BaseSensorsView):
    serializer_class = None

    def post(self, request, provider_key=None):
        """ Add Gate Sensor Observations """
        return GateHandler.post(request, provider_key)


class TestHandlerView(BaseSensorsView):
    serializer_class = None
    permission_classes = (AllowAny,)

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


class KerlinkHandlerView(BaseSensorsView):
    serializer_class = KerlinkHandler.serializer_class

    def post(self, request, provider_key=None):
        return KerlinkHandler.post(request, provider_key)
