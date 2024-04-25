locals {
  domain_parts = regex("(?P<subdomain>[^.]+).(?P<primary_domain>.*)", var.fqdn)
  standard_from_email = "notifications@earthranger.com"

  from_email                = coalesce(var.from_email, local.standard_from_email)
  resolved_eus_organization = coalesce(var.eus_org, var.fqdn)

  db_instance_private_ip = data.terraform_remote_state.site_terraform.outputs.db_instance_private_ip

  tms_api_host = var.tms_api_host != "" ? var.tms_api_host : var.app_infra_workspace == "dev" ? "https://er-tms-api-gateway-5sf422kw.uc.gateway.dev" : "https://er-tms-api-gateway-1r0d2ltk.ew.gateway.dev"

}

resource "template_dir" "deployments" {

  source_dir = "${path.root}/templates"

  destination_dir = "${path.root}/rendered"

  vars = {
    ACCEPT_EULA                     = var.accept_eula
    ALERTS_ENABLED                  = var.alerts_enabled
    ALERTS_RATE_LIMIT               = var.alerts_rate_limit
    ALT_SERVER_NAMES                = join(",", var.alt_server_names)
    API_ENDPOINT                    = var.api_endpoint
    API_HOST                        = var.api_host
    API_PORT                        = var.api_port
    AWS_ACCESS_KEY_ID               = jsondecode(data.google_secret_manager_secret_version.aws_metrics_credentials.secret_data).aws_access_key_id
    AWS_SECRET_ACCESS_KEY           = jsondecode(data.google_secret_manager_secret_version.aws_metrics_credentials.secret_data).aws_secret_access_key
    CLUSTER_NAME                    = var.cluster_name
    CONFIG_CONTAINER                = var.config_container
    DAILY_REPORT_ENABLED            = var.daily_report_enabled
    DB_HOST                         = local.db_instance_private_ip
    DB_NAME                         = var.db_name
    DB_PORT                         = var.db_port
    DB_USER                         = var.db_user
    DEFAULT_EVENT_FILTER_FROM_DAYS  = var.default_event_filter_from_days
    DEFAULT_FROM_EMAIL              = local.from_email
    DEFAULT_PATROL_FILTER_FROM_DAYS = var.default_patrol_filter_from_days
    DJANGO_LOGGING_LEVEL            = var.django_logging_level
    DJANGO_REQUEST_LOGGING_LEVEL    = var.django_request_logging_level
    DJANGO_SERVER_LOGGING_LEVEL     = var.django_server_logging_level
    EMAIL_HOST                      = var.email_host
    EMAIL_HOST_USER                 = var.email_host_user
    ENABLE_DEBUG                    = var.enable_debug
    EUS_EMAIL                       = var.eus_email
    EUS_NAME                        = var.eus_name
    EUS_ORG                         = local.resolved_eus_organization
    EUS_TYPE                        = var.eus_type
    FEATURE_TMS                     = var.feature_tms
    FQDN                            = var.fqdn
    FROM_EMAIL                      = local.from_email
    GEO_PERMISSION_SPEED_KM_H       = var.geo_permission_speed_km_h
    GFW_CLUSTER_RADIUS              = var.gfw_cluster_radius
    GFW_BACKFILL_INTERVAL_DAYS      = var.gfw_backfill_interval_days
    GS_BUCKET_NAME                  = var.gs_bucket_name
    INGRESS_VERSION                 = var.INGRESS_VERSION
    WEB_REACT_VERSION               = var.WEB_REACT_VERSION
    WEB_ADMIN_VERSION               = var.WEB_ADMIN_VERSION
    KML_EXPORT                      = var.kml_export
    KML_OVERLAY_IMAGE               = var.kml_overlay_image
    KML_FEED_TITLE                  = var.kml_feed_title
    KUBERNETES_NAMESPACE            = var.kubernetes_namespace
    MAPBOX_TOKEN                    = var.mapbox_token
    MAPPING_FEATURES_V2             = var.mapping_features_v2
    MEMORY_STORE_HOST               = var.memory_store_host
    MEMORY_STORE_DATABASE           = var.memory_store_database
    MEMORY_STORE_API_KEY            = var.memory_store_api_key
    MEMORY_STORE_PORT               = var.memory_store_port
    OBSERVATION_ACCURACY_THRESHOLD  = var.observation_accuracy_threshold
    PATROL_ENABLED                  = var.patrol_enabled
    ROOT_LOGGING_LEVEL              = var.root_logging_level
    RTAPI_LOGGING_LEVEL             = var.rtapi_logging_level
    RTAPI_PUBSUB_LOGGING_LEVEL      = var.rtapi_pubsub_logging_level
    RTAPI_SOCKET_LOGGING_LEVEL      = var.rtapi_socket_logging_level
    SENDSMS_TWILIO_FROM_NUMBER      = var.sendsms_twilio_from_number
    SERVER_VERSION                  = var.SERVER_VERSION
    SHOW_STATIONARY_SUBJECTS_ON_MAP = var.show_stationary_subjects_on_map
    SHOW_TRACK_DAYS                 = var.show_track_days
    SITE_IP_ADDRESS                 = var.site_ip_address
    SMS_ID                          = var.sms_id
    SMS_TOKEN                       = var.sms_token
    STORAGE_CONTAINER               = var.storage_container
    SUBJECT_REGION_ENABLED          = var.subject_region_enabled
    TABLEAU_DEFAULT_DASHBOARD       = var.tableau_default_dashboard
    TABLEAU_ENABLED                 = var.tableau_enabled
    TABLEAU_SITE_ID                 = var.tableau_site_id
    TIME_ZONE                       = var.time_zone
    TMS_API_HOST                    = local.tms_api_host
    TMS_API_KEY                     = var.tms_api_key
    TRACK_LENGTH                    = var.track_length
    USE_AZURE_STORAGE               = var.use_azure_storage
    WEB_SERVICE_NAME                = var.web_service_name
    GA_MEASUREMENT_ID               = jsondecode(data.google_secret_manager_secret_version.ga_measurement_id.secret_data).ga_measurement_id
  }
}
