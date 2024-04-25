import datetime
import uuid

import environ

from django.conf import settings

from utils.json import parse_bool
from utils.patterns import singleton

from .dataclass import EnvironmentSettings, FeatureFlags, Tenant

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# this reads the .env file in the local dir. You can
# specify specific envs if needed.
environ.Env.read_env(settings.BASE_DIR(".env"))


@singleton
class DjangoSettingsTenantBuilder:
    def __init__(self):
        self.tenant = Tenant(
            id=settings.TENANT_ID,
            cluster_name=None,
            cluster_namespace=None,
            created_at=datetime.datetime.now(tz=datetime.timezone.utc),
            domain=getattr(settings, "SERVER_FQDN", None),
            env_settings=self._load_env_settings_from_django(),
            feature_flags=self._load_feature_flags_from_django(),
            name=getattr(settings, "UI_SITE_NAME", None),
            permissions_custom_sequence_end=env.int("PERMISSIONS_CUSTOMSEQUENCE_END", None),
            permissions_custom_sequence_start=env.int("PERMISSIONS_CUSTOMSEQUENCE_START", None),
            services=[],
            slug_name=getattr(settings, "SERVER_FQDN", None),
            status=None,
            updated_at=datetime.datetime.now(tz=datetime.timezone.utc),
            url=getattr(settings, "UI_SITE_URL", None),
        )

    def build(self) -> Tenant:
        return self.tenant

    def _load_env_settings_from_django(self) -> EnvironmentSettings:
        default_event_filter_from_days = int(getattr(settings, "DEFAULT_EVENT_FILTER_FROM_DAYS", -1))
        default_event_filter_from_days = (
            None if default_event_filter_from_days == -1 else default_event_filter_from_days
        )
        default_patrol_filter_from_days = int(getattr(settings, "DEFAULT_PATROL_FILTER_FROM_DAYS", -1))
        default_patrol_filter_from_days = (
            None if default_patrol_filter_from_days == -1 else default_patrol_filter_from_days
        )

        return EnvironmentSettings(
            accept_eula=parse_bool(settings.ACCEPT_EULA),
            alert_rate_limit=settings.ALERTS_RATE_LIMIT,
            default_event_filter_from_days=default_event_filter_from_days,
            default_patrol_filter_from_days=default_patrol_filter_from_days,
            eus_org=getattr(settings, "EUS_SETTINGS", {}).get("organization"),
            fqdn=settings.SERVER_FQDN,
            patrol_enabled=parse_bool(settings.PATROL_ENABLED),
            tableau_site_id=getattr(settings, "TABLEAU_SITE_ID", None),
            tableau_default_dashboard=getattr(settings, "TABLEAU_DEFAULT_DASHBOARD"),
            show_track_days=int(getattr(settings, "SHOW_TRACK_DAYS", 16)),
            show_stationary_subjects_on_map=parse_bool(getattr(settings, "SHOW_STATIONARY_SUBJECTS_ON_MAP", True)),
            gs_bucket_name=getattr(settings, "GS_BUCKET_NAME", None),
            geo_permission_radius_meters=int(getattr(settings, "GEO_PERMISSION_RADIUS_METERS")),
            geo_permission_speed_km_h=int(getattr(settings, "GEO_PERMISSION_SPEED_KM_H")),
            geo_permission_violation_ban_duration_min=int(getattr(settings, "GEO_PERMISSION_BAN_DURATON_MIN", 0)),
            subject_region_enabled=parse_bool(getattr(settings, "SUBJECT_REGION_ENABLED", True)),
            track_length=int(settings.TRACK_LENGTH),
            observation_accuracy_threshold=int(settings.OBSERVATION_ACCURACY_THRESHOLD),
        )

    def _load_feature_flags_from_django(self) -> FeatureFlags:
        return FeatureFlags(
            alerts_enabled=parse_bool(settings.ALERTS_ENABLED),
            daily_report_enabled=parse_bool(settings.DAILY_REPORT_ENABLED),
            kml_export=parse_bool(settings.EXPORT_KML_ENABLED),
            mapping_features_v2=True,
            tableau_enabled=parse_bool(settings.TABLEAU_ENABLED),
            tableau_site_id=parse_bool(getattr(settings, "TABLEAU_SITE_ID", None)),
            track_length=parse_bool(settings.TRACK_LENGTH),
        )
