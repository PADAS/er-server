import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from dataclasses_json import config, dataclass_json


@dataclass_json
@dataclass
class EnvironmentSettings:
    accept_eula: Optional[bool] = field(metadata=config(field_name="acceptEula"), default=False)
    all_server_names: Optional[List[str]] = field(metadata=config(field_name="allServerNames"), default=None)
    default_event_filter_from_days: Optional[int] = field(
        metadata=config(field_name="defaultEventFilterFromDays"), default=None
    )
    default_patrol_filter_from_days: Optional[int] = field(
        metadata=config(field_name="defaultPatrolFilterFromDays"), default=None
    )
    eus_org: Optional[str] = field(metadata=config(field_name="eusOrg"), default=None)
    fqdn: Optional[str] = field(metadata=config(field_name="fqdn"), default=None)
    gd_bucket_name: Optional[str] = field(metadata=config(field_name="gsBucketName"), default=None)
    geo_permission_radius_meters: Optional[int] = field(
        metadata=config(field_name="geoPermissionRadiusMeters"), default=3704
    )
    geo_permission_speed_km_h: Optional[int] = field(metadata=config(field_name="geoPermissionSpeedKmH"), default=75)
    geo_permission_violation_ban_duration_min: Optional[int] = field(
        metadata=config(field_name="geoPermissionViolationBanDurationMin"), default=10
    )
    kml_feed_title: Optional[str] = field(metadata=config(field_name="kmlFeedTitle"), default="EarthRanger KML service")
    kml_overlay_image: Optional[str] = field(metadata=config(field_name="kmlOverlayImage"), default=None)
    observation_accuracy_threshold: Optional[int] = field(
        metadata=config(field_name="observationAccuracyThreshold"), default=None
    )
    patrol_enabled: Optional[bool] = field(metadata=config(field_name="patrolEnabled"), default=False)
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
    daily_report_enabled: Optional[bool] = field(metadata=config(field_name="dailyReportEnabled"), default=False)
    kml_export: Optional[bool] = field(metadata=config(field_name="kmlExport"), default=False)
    mapping_features_v2: Optional[bool] = field(metadata=config(field_name="mappingFeaturesV2"), default=False)
    tableau_enabled: Optional[bool] = field(metadata=config(field_name="tableauEnabled"), default=False)
    tableau_site_id: Optional[bool] = field(metadata=config(field_name="tableauSiteId"), default=False)
    track_length: Optional[bool] = field(metadata=config(field_name="trackLength"), default=False)


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
