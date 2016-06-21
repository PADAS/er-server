from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from sensors.handlers import GsatHandler, DasRadioAgentHandler

class AllowAnyGet(BasePermission):

    def has_permission(self, request, view):
        return request.method in ('GET', 'HEAD', 'OPTIONS') \
            or (request.user and request.user.is_authenticated())

class SensorObservation(generics.GenericAPIView):

    permission_classes = (AllowAnyGet, )

    def get(self, request, *args, sensor_type=None, provider_key=None, **kwargs):

        if sensor_type == GsatHandler.SENSOR_TYPE:
            return GsatHandler().handle_observation(request, provider_key)

        # TODO: Write a validator to do this error response.
        errordata = {
            'data':
                {'sensor_type': _('{} is not a valid sensor_type').format(sensor_type)}
        }

        return Response(data=errordata, status=status.HTTP_400_BAD_REQUEST)


    def post(self, request, *args, sensor_type=None, provider_key=None, **kwargs):
        if sensor_type == DasRadioAgentHandler.SENSOR_TYPE:
            return DasRadioAgentHandler.handle_observation(request, provider_key)

        # TODO: Write a validator to do this error response.
        errordata = {
            'data':
                {'sensor_type': _('{} is not a valid sensor_type').format(sensor_type)}
        }

        return Response(data=errordata, status=status.HTTP_400_BAD_REQUEST)

