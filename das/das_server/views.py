import copy
from datetime import datetime, timedelta

import pytz

# from rest_framework.schemas.openapi import AutoSchema
from drf_spectacular.openapi import AutoSchema
from oauth2_provider.models import get_access_token_model, get_application_model
from oauthlib.common import generate_token

from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView
from rest_framework import generics
from rest_framework.permissions import AllowAny

from activity.alerts import has_alerts_permissionset, has_patrol_view_permission

# from activity.serializers import LeaderRelatedField, PatrolList
# from activity.serializers.fields import DateTimeRangeField
from core.utils import get_site_name

# This import ensures we register user-login receivers.
from das_server import __version__
from das_server.serializers import VersionSerializer
from observations import servicesutils
from observations.servicesutils import has_message_view_permission
from utils.json import parse_bool
from utils.tenant import get_tenant_settings

# from rest_framework.serializers import ChoiceField


CLIENT_ID = "das_web_client"
AccessToken = get_access_token_model()
Application = get_application_model()


def index(request):
    return render("www/index.html", request)


class CustomSchema(AutoSchema):

    def map_field(self, field):
        if isinstance(field, PointField):
            return {"type": "object", "properties": {"latitude": {"type": "string"}, "longitude": {"type": "string"}}}
        if isinstance(field, DateTimeRangeField):
            return {
                "type": "object",
                "properties": {
                    "start_time": {"type": "string", "format": "date-time"},
                    "end_time": {"type": "string", "format": "date-time"},
                },
            }

    #     if isinstance(field, ChoiceField):
    #         return {"type": "integer" if isinstance(field.default, int) else "string"}

    #     if isinstance(field, LeaderRelatedField):
    #         return {"type": "object", "properties": {}}

        if isinstance(field, PatrolList):
            return {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid", "readOnly": True},
                    "title": {"type": "string", "maxLength": 255},
                    "priority": {"type": "integer"},
                    "state": {"type": "string", "maxLength": 255},
                },
            }
        return super().map_field(field)

    def get_tags(self, path, method):
        return [self._view.__module__.split(".")[0].replace("_", " ").title()]


class StatusView(generics.RetrieveAPIView):
    """
    What is the server status and current api version.
    ---

    """

    permission_classes = (AllowAny,)
    serializer_class = VersionSerializer

    def get_object(self):
        resp = {"version": __version__}  # request.version}

        tenant = get_tenant_settings()
        resp["alerts_enabled"] = tenant.feature_flags.alerts_enabled and has_alerts_permissionset(self.request.user)
        resp["daily_report_enabled"] = tenant.feature_flags.daily_report_enabled
        resp["eula_enabled"] = tenant.env_settings.accept_eula
        resp["export_kml_enabled"] = tenant.feature_flags.kml_export
        resp["patrol_enabled"] = tenant.env_settings.patrol_enabled and has_patrol_view_permission(self.request.user)
        resp["show_stationary_subjects_on_map"] = tenant.env_settings.show_stationary_subjects_on_map
        resp["show_track_days"] = tenant.env_settings.show_track_days
        resp["tableau_enabled"] = self.request.user.is_superuser and tenant.feature_flags.tableau_enabled
        resp["track_length"] = tenant.env_settings.track_length

        default_event_filter_from_days = tenant.env_settings.default_event_filter_from_days
        if default_event_filter_from_days and default_event_filter_from_days >= 0:
            resp["default_event_filter_from_days"] = tenant.env_settings.default_event_filter_from_days

        default_patrol_filter_from_days = tenant.env_settings.default_patrol_filter_from_days
        if default_patrol_filter_from_days and default_patrol_filter_from_days >= 0:
            resp["default_patrol_filter_from_days"] = tenant.env_settings.default_patrol_filter_from_days

        resp["event_matrix_enabled"] = settings.EVENT_MATRIX_ENABLED
        resp["event_search_enabled"] = True
        resp["server_timezone_name"] = timezone.get_current_timezone_name()
        resp["server_timezone"] = timezone.localtime().strftime("%Z")
        resp["site_name"] = get_site_name()
        resp["tenant_domain"] = tenant.domain
        resp["messaging_enabled"] = has_message_view_permission(self.request.user)

        if self.get_support_settings():
            resp["eus_settings"] = self.get_support_settings()

        if parse_bool(self.request.query_params.get("db_connections")):
            resp["db_connection_count"] = self.get_used_db_connections()
            last_migration = self.get_last_migration()
            resp["last_migration_app"] = last_migration.app
            resp["last_migration_name"] = last_migration.name

        if parse_bool(self.request.query_params.get("service_status")):
            resp["services"] = servicesutils.get_source_provider_statuses()

        return resp

    def get_used_db_connections(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity;")
            row = cursor.fetchone()
            return row[0]

    def get_support_settings(self):
        try:
            if settings.EUS_SETTINGS["type"]:
                return copy.copy(settings.EUS_SETTINGS)
        except (KeyError, AttributeError):
            pass

    def get_last_migration(self):
        return MigrationRecorder.Migration.objects.latest("id")


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
        context["token"] = token
        context["schema_url"] = "openapi-schema"
        return context

    def _get_token(self):
        ttl = getattr(settings, "ACCESS_TOKEN_EXPIRE_SECONDS", 3600 * 48)  # this value is in seconds
        expire = datetime.now(tz=pytz.utc) + timedelta(seconds=ttl)
        return AccessToken.objects.create(
            user=self.request.user,
            token=generate_token(),
            application=self.application,
            scope="read write",
            expires=expire,
        )
