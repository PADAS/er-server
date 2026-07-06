import datetime
import logging
from typing import Optional

import environ

from django.conf import settings

from utils.json import parse_bool
from utils.patterns import singleton

from .dataclass import EnvironmentSettings, FeatureFlags, GeoSpan, Tenant

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

# this reads the .env file in the local dir. You can
# specify specific envs if needed.
environ.Env.read_env(settings.BASE_DIR(".env"))

logger = logging.getLogger(__name__)


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
            preview_features=dict(getattr(settings, "PREVIEW_FEATURES", {}) or {}),
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
            alert_rate_limit=int(settings.ALERTS_RATE_LIMIT),
            events_create_throttle_rate=getattr(settings, "EVENTS_CREATE_THROTTLE_RATE", "600/min") or None,
            events_create_max_concurrency=getattr(settings, "EVENTS_CREATE_MAX_CONCURRENCY", 10),
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
            geo_permission_violation_ban_duration_min=int(
                getattr(settings, "GEO_PERMISSION_VIOLATION_BAN_DURATION_MIN", 0)
            ),
            subject_region_enabled=parse_bool(getattr(settings, "SUBJECT_REGION_ENABLED", True)),
            track_length=int(settings.TRACK_LENGTH),
            observation_accuracy_threshold=int(settings.OBSERVATION_ACCURACY_THRESHOLD),
            alt_server_names=getattr(settings, "ALT_SERVER_NAMES", None),
            geo_span=self._load_geo_span_from_django(),
        )

    def _load_geo_span_from_django(self) -> Optional[GeoSpan]:
        geo_span = getattr(settings, "GEO_SPAN", None)
        if not geo_span:
            return None

        if not isinstance(geo_span, dict):
            logger.warning("GEO_SPAN must be a dict with 'lat' and 'lon' keys, got %r", geo_span)
            return None

        def _convert_float_pair(value, name):
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                logger.warning("GEO_SPAN: '%s' must be a 2-element array, got %r", name, value)
                return None
            try:
                return [float(value[0]), float(value[1])]
            except (TypeError, ValueError):
                logger.warning("GEO_SPAN: '%s' values must be convertible to float, got %r", name, value)
                return None

        lat = _convert_float_pair(geo_span.get("lat"), "lat")
        lon = _convert_float_pair(geo_span.get("lon"), "lon")
        if lat is None or lon is None:
            return None

        if lat[1] < lat[0] or lon[1] < lon[0]:
            logger.warning("GEO_SPAN: max values must be greater than or equal to min values, got %r", geo_span)
            return None

        return GeoSpan(lat=lat, lon=lon)

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
