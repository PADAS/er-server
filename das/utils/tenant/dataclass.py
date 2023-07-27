import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from dataclasses_json import config, dataclass_json


@dataclass_json
@dataclass
class EnvironmentSettings:
    accept_eula: bool = field(metadata=config(field_name="acceptEula"))
    api_host: str = field(metadata=config(field_name="apiHost"))
    api_port: str = field(metadata=config(field_name="apiPort"))
    default_from_email: str = field(metadata=config(field_name="defaultFromEmail"))
    enable_debug: bool = field(metadata=config(field_name="enableDebug"))
    enable_dev: bool = field(metadata=config(field_name="enableDev"))
    from_email: str = field(metadata=config(field_name="fromEmail"))
    send_sms_twilio_from_number: str = field(metadata=config(field_name="sendSmsTwilioFromNumber"))
    alerts_rate_limit: Optional[int] = field(metadata=config(field_name="alertsRateLimit"), default=20)


@dataclass_json
@dataclass
class FeatureFlags:
    alerts_enabled: Optional[bool] = field(metadata=config(field_name="alertsEnabled"), default=False)
    daily_report_enabled: Optional[bool] = field(metadata=config(field_name="dailyReportEnabled"), default=False)
    gfw_back_fill_interval_days: Optional[bool] = field(
        metadata=config(field_name="gfwBackfillIntervalDays"), default=False
    )
    gfw_cluster_radius: Optional[bool] = field(metadata=config(field_name="gfwClusterRadius"), default=False)
    kml_export: Optional[bool] = field(metadata=config(field_name="kmlExport"), default=False)
    mapping_features_v2: Optional[bool] = field(metadata=config(field_name="mappingFeaturesV2"), default=False)
    patrol_enabled: Optional[bool] = field(metadata=config(field_name="patrolEnabled"), default=False)
    show_stationary_subjects_on_map: Optional[bool] = field(
        metadata=config(field_name="showStationarySubjectsOnMap"), default=False
    )
    show_track_days: Optional[bool] = field(metadata=config(field_name="showTrackDays"), default=False)
    subject_region_enabled: Optional[bool] = field(metadata=config(field_name="subjectRegionEnabled"), default=True)
    tableau_default_dashboard: Optional[bool] = field(
        metadata=config(field_name="tableauDefaultDashboard"), default=False
    )
    tableau_enabled: Optional[bool] = field(metadata=config(field_name="tableauEnabled"), default=False)
    tableau_site_id: Optional[bool] = field(metadata=config(field_name="tableauSiteId"), default=False)
    track_length: Optional[bool] = field(metadata=config(field_name="trackLength"), default=False)


@dataclass_json
@dataclass
class Service:
    status: str = field(metadata=config(field_name="status"))
    status_message: str = field(metadata=config(field_name="statusMessage"), default=None)


class Services:
    auth: Service = field(metadata=config(field_name="auth"))
    big_query: Service = field(metadata=config(field_name="bigQuery"))
    data_warehouse: Service = field(metadata=config(field_name="dataWarehouse"))
    media: Service = field(metadata=config(field_name="media"))
    observations: Service = field(metadata=config(field_name="observations"))
    secrets: Service = field(metadata=config(field_name="secrets"))


@dataclass_json
@dataclass
class Tenant:
    id: uuid = field(metadata=config(field_name="id"))
    domain: str = field(metadata=config(field_name="domain"))
    name: str = field(metadata=config(field_name="name"))
    time_zone: str = field(metadata=config(field_name="timeZone"))
    url: str = field(metadata=config(field_name="url"))
    feature_flags: str = field(metadata=config(field_name="featureFlags"))
    env_settings: EnvironmentSettings = field(metadata=config(field_name="envSettings"))
    feature_flags: FeatureFlags
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
    services: Services = field(metadata=config(field_name="services"))
    slug_name: Optional[str] = field(metadata=config(field_name="slugName"), default=None)
    status: Optional[str] = field(metadata=config(field_name="status"), default=None)
