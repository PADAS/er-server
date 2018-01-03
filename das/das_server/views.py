import copy

from django.shortcuts import render_to_response
from django.conf import settings
from django.db import connection
from django.template import RequestContext
from rest_framework import generics
from rest_framework.permissions import AllowAny, DjangoObjectPermissions
import rest_framework.serializers

from das_server import __version__
from utils.json import parse_bool


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
    db_connection_count = rest_framework.serializers.IntegerField(
        read_only=True)
    eus_settings = rest_framework.serializers.DictField(read_only=True)


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

        if self.get_support_settings():
            resp['eus_settings'] = self.get_support_settings()

        if parse_bool(self.request.query_params.get('db_connections')):
            resp['db_connection_count'] = self.get_used_db_connections()
        return resp

    def get_used_db_connections(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity;")
            row = cursor.fetchone()
            return row[0]

    def get_support_settings(self):
        try:
            if settings.EUS_SETTINGS['type']:
                return copy.copy(settings.EUS_SETTINGS)
        except (KeyError, AttributeError):
            pass
