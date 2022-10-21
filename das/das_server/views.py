import copy
from datetime import datetime, timedelta

import pytz
from drf_extra_fields.geo_fields import PointField
from oauth2_provider.models import AccessToken, Application
from oauthlib.common import generate_token

import rest_framework.serializers
from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.serializers import ChoiceField

from activity.alerts import (has_alerts_permissionset,
                             has_patrol_view_permission)
from activity.serializers.fields import DateTimeRangeField
from activity.serializers.patrol_serializers import (LeaderRelatedField,
                                                     PatrolList)
from core.utils import get_site_name
# This import ensures we register user-login receivers.
from das_server import __version__
from observations import servicesutils
from observations.servicesutils import has_message_view_permission
from utils.json import parse_bool

CLIENT_ID = "das_web_client"


def index(request):
    return render('www/index.html', request)


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
        # Patch get_serializer_class to use views class if no serializer class
        # is defined
        if hasattr(self.view, 'get_serializer_class'):
            self.view.get_serializer_class = self.get_serializer_class

        return super()._get_operation_id(path, method)

    def _map_serializer(self, serializer):

        # update default values to be json serializable
        result = super()._map_serializer(serializer)
        for res in result.get('properties').values():
            if res.get('default'):
                try:
                    res['default'] = res['default']()
                except Exception:
                    pass

        # add required field to result to fix the break when clearing the same
        # field for a patch method in _get_request_body.
        for method in self._view.allowed_methods:
            if method == 'PATCH' and 'required' not in result:
                result['required'] = []
        return result

    def _map_field(self, field):
        if isinstance(field, PointField):
            return {
                'type': 'object',
                'properties': {'latitude': {'type': 'string'},
                               'longitude': {'type': 'string'}}
            }
        if isinstance(field, DateTimeRangeField):
            return {
                'type': 'object',
                'properties': {'start_time': {'type': 'string', 'format': 'date-time'},
                               'end_time': {'type': 'string', 'format': 'date-time'}}
            }

        if isinstance(field, ChoiceField):
            return {'type': 'integer' if isinstance(field.default, int) else 'string'}

        if isinstance(field, LeaderRelatedField):
            return {'type': 'object', 'properties': {}}

        if isinstance(field, PatrolList):
            return {
                'type': 'object',
                "properties": {
                    "id": {"type": "string", "format": "uuid", "readOnly": True},
                    "title": {"type": "string", "maxLength": 255},
                    'priority': {"type": "integer"},
                    'state': {"type": "string", "maxLength": 255},
                }
            }
        return super()._map_field(field)


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
    tableau_enabled = rest_framework.serializers.BooleanField(
        read_only=True)

    services = rest_framework.serializers.ListField(read_only=True)

    server_timezone_name = rest_framework.serializers.CharField(read_only=True)
    server_timezone = rest_framework.serializers.CharField(read_only=True)

    eula_enabled = rest_framework.serializers.BooleanField(read_only=True)
    patrol_enabled = rest_framework.serializers.BooleanField(read_only=True)
    messaging_enabled = rest_framework.serializers.BooleanField(read_only=True)
    site_name = rest_framework.serializers.CharField(read_only=True)
    last_migration_app = rest_framework.serializers.CharField(read_only=True)
    last_migration_name = rest_framework.serializers.CharField(read_only=True)
    track_length = rest_framework.serializers.IntegerField(read_only=True)


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

        resp['alerts_enabled'] = settings.ALERTS_ENABLED and has_alerts_permissionset(
            self.request.user)
        resp['tableau_enabled'] = self.request.user.is_superuser and settings.TABLEAU_ENABLED

        resp['server_timezone_name'] = timezone.get_current_timezone_name()
        resp['server_timezone'] = timezone.localtime().strftime('%Z')
        resp['site_name'] = get_site_name()
        resp['eula_enabled'] = settings.ACCEPT_EULA
        resp['patrol_enabled'] = settings.PATROL_ENABLED and has_patrol_view_permission(
            self.request.user)
        resp['track_length'] = settings.TRACK_LENGTH
        resp['messaging_enabled'] = has_message_view_permission(
            self.request.user)

        if self.get_support_settings():
            resp['eus_settings'] = self.get_support_settings()

        if parse_bool(self.request.query_params.get('db_connections')):
            resp['db_connection_count'] = self.get_used_db_connections()
            last_migration = self.get_last_migration()
            resp['last_migration_app'] = last_migration.app
            resp['last_migration_name'] = last_migration.name

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

    def get_last_migration(self):
        return MigrationRecorder.Migration.objects.latest('id')


class SwaggerTemplate(TemplateView):
    template_name = "swagger-ui.html"

    def __init__(self) -> None:
        super().__init__()
        self.application = Application.objects.get(client_id=CLIENT_ID)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token = None
        if self.request.user.is_authenticated:
            token = self._get_token()
        context['token'] = token
        context['schema_url'] = "openapi-schema"
        return context

    def _get_token(self):
        ttl = getattr(settings, 'ACCESS_TOKEN_EXPIRE_SECONDS', 3600 * 48)
        expire = datetime.now(tz=pytz.utc) + timedelta(days=ttl)
        return AccessToken.objects.create(
            user=self.request.user, token=generate_token(),
            application=self.application, scope='read write',
            expires=expire,
        )
