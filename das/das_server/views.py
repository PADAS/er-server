from django.shortcuts import render_to_response
from django.conf import settings
from django.template import RequestContext
from rest_framework import generics
from rest_framework.permissions import AllowAny, DjangoObjectPermissions
import rest_framework.serializers

from das_server import __version__


def index(request):
    return render_to_response('www/index.html')


class VersionSerializer(rest_framework.serializers.Serializer):
    version = rest_framework.serializers.CharField(read_only=True)
    event_matrix_enabled = rest_framework.serializers.BooleanField(
        read_only=True)
    event_search_enabled = rest_framework.serializers.BooleanField(
        read_only=True)
    export_kml_enabled = rest_framework.serializers.BooleanField(
        read_only=True)


class StatusView(generics.RetrieveAPIView):
    """
    What is the server status and current api version.
    ---

    """
    permission_classes = (AllowAny,)
    serializer_class = VersionSerializer

    def get_object(self):
        resp = {'version': __version__}  # request.version}

        resp['event_matrix_enabled'] = settings.EVENT_MATRIX_ENABLED
        resp['export_kml_enabled'] = settings.EXPORT_KML_ENABLED

        resp['event_search_enabled'] = True
        return resp
