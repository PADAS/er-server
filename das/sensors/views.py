from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny

from sensors.handlers import GsatHandler

@api_view(['GET', 'POST'])
@permission_classes((AllowAny,))
def sensor_observations(request, sensor_type=None, provider_key=None):
    """
    General handler for inbound sensor data. First version is for GSAT relay for GSE Nano devices deployed in Lewa/NRT.

    The sensor_type will identify the handler to use for processing the request.
    The provider_key identifies the unique provider that is submitting data.
    """

    if request.method == 'GET':

        if sensor_type == GsatHandler.SENSOR_TYPE:
            return GsatHandler.handle_observation(request, provider_key)

