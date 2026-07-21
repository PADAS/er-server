import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from dataclasses_json import config, dataclass_json


@dataclass_json
@dataclass
class GeoSpan:
    """Geographic bounding box defined by latitude and longitude ranges.

    Attributes:
        lat: Latitude bounds in degrees as a two-element list [min_lat, max_lat].
            Expected range is -90.0 <= min_lat <= max_lat <= 90.0.
        lon: Longitude bounds in degrees as a two-element list [min_lon, max_lon].
            Expected range is -180.0 <= min_lon <= max_lon <= 180.0.

    The first element of each list is the minimum bound, and the second is the maximum bound.
    """

    lat: List[float] = field(metadata=config(field_name="lat"), default_factory=lambda: [-90.0, 90.0])
    lon: List[float] = field(metadata=config(field_name="lon"), default_factory=lambda: [-180.0, 180.0])


DEFAULT_COMMUNITY_INPUT_ALLOWED_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/bmp",
    "image/tiff",
    "video/*",
    "audio/*",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "text/plain",
    "text/csv",
)


@dataclass_json
@dataclass
class EnvironmentSettings:
    accept_eula: Optional[bool] = field(metadata=config(field_name="acceptEula"), default=True)
    alert_rate_limit: int = field(metadata=config(field_name="alertRateLimit"), default=20)
    all_server_names: Optional[List[str]] = field(metadata=config(field_name="allServerNames"), default=None)
    alt_server_names: Optional[List[str]] = field(metadata=config(field_name="altServerNames"), default=None)
    community_input_allowed_mime_types: Optional[List[str]] = field(
        metadata=config(field_name="communityInputAllowedMimeTypes"),
        default_factory=lambda: list(DEFAULT_COMMUNITY_INPUT_ALLOWED_MIME_TYPES),
    )
    community_input_event_throttle_rate: Optional[str] = field(
        metadata=config(field_name="communityInputEventThrottleRate"), default="120/hour"
    )
    community_input_file_throttle_rate: Optional[str] = field(
        metadata=config(field_name="communityInputFileThrottleRate"), default="60/hour"
    )
    events_create_throttle_rate: Optional[str] = field(
        metadata=config(field_name="eventsCreateThrottleRate"), default="600/min"
    )
    events_create_max_concurrency: Optional[int] = field(
        metadata=config(field_name="eventsCreateMaxConcurrency"), default=10
    )
    community_input_max_upload_bytes: Optional[int] = field(
        metadata=config(field_name="communityInputMaxUploadBytes"), default=20 * 1024 * 1024
    )
    community_input_note_throttle_rate: Optional[str] = field(
        metadata=config(field_name="communityInputNoteThrottleRate"), default="120/hour"
    )
    community_input_read_throttle_rate: Optional[str] = field(
        metadata=config(field_name="communityInputReadThrottleRate"), default="1200/hour"
    )
    default_event_filter_from_days: Optional[int] = field(
        metadata=config(field_name="defaultEventFilterFromDays"), default=None
    )
    default_patrol_filter_from_days: Optional[int] = field(
        metadata=config(field_name="defaultPatrolFilterFromDays"), default=None
    )
    eus_org: Optional[str] = field(metadata=config(field_name="eusOrg"), default=None)
    fqdn: Optional[str] = field(metadata=config(field_name="fqdn"), default=None)
    gs_bucket_name: Optional[str] = field(metadata=config(field_name="gsBucketName"), default=None)
    geo_permission_radius_meters: Optional[int] = field(
        metadata=config(field_name="geoPermissionRadiusMeters"), default=3704
    )
    geo_permission_speed_km_h: Optional[int] = field(metadata=config(field_name="geoPermissionSpeedKmH"), default=75)
    geo_permission_violation_ban_duration_min: Optional[int] = field(
        metadata=config(field_name="geoPermissionViolationBanDurationMin"), default=10
    )
    geo_span: Optional[GeoSpan] = field(metadata=config(field_name="geoSpan"), default=None)
    kml_feed_title: Optional[str] = field(metadata=config(field_name="kmlFeedTitle"), default="EarthRanger KML service")
    kml_overlay_image: Optional[str] = field(metadata=config(field_name="kmlOverlayImage"), default=None)
    observation_accuracy_threshold: Optional[int] = field(
        metadata=config(field_name="observationAccuracyThreshold"), default=None
    )
    patrol_enabled: Optional[bool] = field(metadata=config(field_name="patrolEnabled"), default=True)
    show_stationary_subjects_on_map: Optional[bool] = field(
        metadata=config(field_name="showStationarySubjectsOnMap"), default=False
    )
    show_track_days: Optional[int] = field(metadata=config(field_name="showTrackDays"), default=16)
    subject_region_enabled: Optional[bool] = field(metadata=config(field_name="subjectRegionEnabled"), default=True)
    tableau_default_dashboard: Optional[str] = field(
        metadata=config(field_name="tableauDefaultDashboard"), default=None
    )
    tableau_site_id: Optional[str] = field(metadata=config(field_name="tableauSiteId"), default=None)
    track_length: Optional[int] = field(metadata=config(field_name="trackLength"), default=21)


@dataclass_json
@dataclass
class FeatureFlags:
    alerts_enabled: Optional[bool] = field(metadata=config(field_name="alertsEnabled"), default=False)
    buoy_api_enabled: Optional[bool] = field(metadata=config(field_name="buoyApiEnabled"), default=False)
    daily_report_enabled: Optional[bool] = field(metadata=config(field_name="dailyReportEnabled"), default=False)
    kml_export: Optional[bool] = field(metadata=config(field_name="kmlExport"), default=False)
    mapping_features_v2: Optional[bool] = field(metadata=config(field_name="mappingFeaturesV2"), default=False)
    tableau_enabled: Optional[bool] = field(metadata=config(field_name="tableauEnabled"), default=False)
    tableau_site_id: Optional[bool] = field(metadata=config(field_name="tableauSiteId"), default=False)
    track_length: Optional[bool] = field(metadata=config(field_name="trackLength"), default=False)
    events_enabled: Optional[bool] = field(metadata=config(field_name="eventsEnabled"), default=True)
    subjects_enabled: Optional[bool] = field(metadata=config(field_name="subjectsEnabled"), default=True)
    spatial_features_enabled: Optional[bool] = field(metadata=config(field_name="spatialFeaturesEnabled"), default=True)
    analyzers_enabled: Optional[bool] = field(metadata=config(field_name="analyzersEnabled"), default=True)
    require_idp: Optional[bool] = field(metadata=config(field_name="requireIdp"), default=False)
    idp_org_id: Optional[str] = field(metadata=config(field_name="idpOrgId"), default=None)
    require_mfa: Optional[bool] = field(metadata=config(field_name="requireMfa"), default=False)
    # 365 days: default which doesn't break mobile users in the field since it aligns with mobile token ttl.
    # Keep this value in sync with accounts.mfa.DEFAULT_MFA_MAX_AGE_SECONDS (utils must not import accounts).
    mfa_max_age_seconds: Optional[int] = field(metadata=config(field_name="mfaMaxAgeSeconds"), default=31_536_000)


@dataclass_json
@dataclass
class Service:
    status: str = field(metadata=config(field_name="status"), default="PROVISIONING")
    status_message: Optional[str] = field(metadata=config(field_name="statusMessage"), default=None)


class Services:
    auth: Service = field(metadata=config(field_name="auth"))
    media: Service = field(metadata=config(field_name="media"))


@dataclass_json
@dataclass
class Tenant:
    id: Optional[uuid.UUID] = field(metadata=config(field_name="id"))
    name: str = field(metadata=config(field_name="name"))
    slug_name: str = field(metadata=config(field_name="slugName"))
    cluster_name: Optional[str] = field(metadata=config(field_name="clusterName"))
    cluster_namespace: Optional[str] = field(metadata=config(field_name="clusterNamespace"))
    permissions_custom_sequence_start: Optional[int] = field(
        metadata=config(field_name="permissionsCustomSequenceStart")
    )
    permissions_custom_sequence_end: Optional[int] = field(metadata=config(field_name="permissionsCustomSequenceEnd"))
    domain: str = field(metadata=config(field_name="domain"))
    url: str = field(metadata=config(field_name="url"))
    created_at: datetime = field(
        metadata=config(
            field_name="createdAt",
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
        )
    )
    updated_at: datetime = field(
        metadata=config(
            field_name="updatedAt",
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
        )
    )
    feature_flags: FeatureFlags = field(metadata=config(field_name="featureFlags"))
    env_settings: EnvironmentSettings = field(metadata=config(field_name="envSettings"))
    services: Services = field(metadata=config(field_name="services"))
    status: Optional[str] = field(metadata=config(field_name="status"), default=None)
    preview_features: dict = field(metadata=config(field_name="previewFeatures"), default_factory=dict)
