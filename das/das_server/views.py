import copy

from django.shortcuts import render_to_response
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.template import RequestContext
from rest_framework import generics
from rest_framework.permissions import AllowAny, DjangoObjectPermissions
import rest_framework.serializers
from rest_framework.schemas.openapi import AutoSchema
from das_server import __version__

from activity.alerts import has_alerts_permissionset

# This import ensures we register user-login receivers.
from das_server import metrics

from observations import servicesutils
from utils.json import parse_bool


def index(request):
    return render_to_response('www/index.html')


class CustomSchema(AutoSchema):
    def get_operation(self, path, method):
        # Add operation tags and summary to schema
        operation = super().get_operation(path, method)
        operation['tags'] = [self._view.__module__.split('.')[0]]
        operation['summary'] = getattr(self.view, method.lower()).__doc__

        return operation

    def get_serializer_class(self):
        if self.view.serializer_class:
            return self.view.serializer_class
        else:
            return self.view.__class__

    def _get_operation_id(self, path, method):
        # Patch get_serializer_class to use views class if no serializer class is defined
        if hasattr(self.view, 'get_serializer_class'):
            self.view.get_serializer_class = self.get_serializer_class

        return super()._get_operation_id(path, method)

    def _map_serializer(self, serializer):

        # update default values to be json serializable
        result = super()._map_serializer(serializer)
        for res in result.get('properties').values():
            default = res.get('default')
            if default:
                res['default'] = [] if default == type([]) else {} if default == type({}) else default

        
        # add required field to result to fix the break when clearing the same field for a patch method in _get_request_body.
        for method in self._view.allowed_methods:
            if method == 'PATCH' and 'required' not in result:
                result['required'] = []
        return result


class VersionSerializer(rest_framework.serializers.Serializer):
    version = rest_framework.serializers.CharField(read_only=True)
    show_track_days = rest_framework.serializers.IntegerField(
        read_only=True)
    event_matrix_enabled = rest_framework.serializers.BooleanField(
        read_only=True)
    event_search_enabled = rest_framework.serializers.BooleanField(
        read_only=True)
    export_kml_enabled = rest_framework.serializers.BooleanField(
        read_only=True)
    db_connection_count = rest_framework.serializers.IntegerField(
        read_only=True)
    eus_settings = rest_framework.serializers.DictField(read_only=True)

    show_stationary_subjects_on_map = rest_framework.serializers.BooleanField(
        read_only=True)

    daily_report_enabled = rest_framework.serializers.BooleanField(
        read_only=True)

    alerts_enabled = rest_framework.serializers.BooleanField(
        read_only=True)

    services = rest_framework.serializers.ListField(read_only=True)

    server_timezone_name = rest_framework.serializers.CharField(read_only=True)
    server_timezone = rest_framework.serializers.CharField(read_only=True)

    eula_enabled = rest_framework.serializers.BooleanField(read_only=True)


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
        resp['show_track_days'] = settings.SHOW_TRACK_DAYS
        resp['event_search_enabled'] = True
        resp['show_stationary_subjects_on_map'] = settings.SHOW_STATIONARY_SUBJECTS_ON_MAP
        resp['daily_report_enabled'] = settings.DAILY_REPORT_ENABLED

        resp['alerts_enabled'] = settings.ALERTS_ENABLED and has_alerts_permissionset(self.request.user)

        resp['server_timezone_name'] = timezone.get_current_timezone_name()
        resp['server_timezone'] = timezone.localtime().strftime('%Z')
        resp['eula_enabled'] = settings.ACCEPT_EULA

        if self.get_support_settings():
            resp['eus_settings'] = self.get_support_settings()

        if parse_bool(self.request.query_params.get('db_connections')):
            resp['db_connection_count'] = self.get_used_db_connections()

        if parse_bool(self.request.query_params.get('service_status')):
            resp['services'] = servicesutils.get_source_provider_statuses()

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
