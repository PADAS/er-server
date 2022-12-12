locals {
  domain_parts = regex("(?P<subdomain>[^.]+).(?P<primary_domain>.*)", var.fqdn)
  standard_from_email = join("", ["notifications.", local.domain_parts["subdomain"],
  "@", local.domain_parts["primary_domain"]])

  from_email                = coalesce(var.from_email, local.standard_from_email)
  resolved_eus_organization = coalesce(var.eus_org, var.fqdn)

  db_instance_private_ip = data.terraform_remote_state.site_terraform.outputs.db_instance_private_ip

}

resource "template_dir" "deployments" {

  source_dir = "${path.root}/templates"

  destination_dir = "${path.root}/rendered"

  vars = {
    ACCEPT_EULA                     = var.accept_eula
    ALERTS_ENABLED                  = var.alerts_enabled
    ALT_SERVER_NAMES                = join(",", var.alt_server_names)
    API_ENDPOINT                    = var.api_endpoint
    API_HOST                        = var.api_host
    API_PORT                        = var.api_port
    AWS_ACCESS_KEY_ID               = jsondecode(data.google_secret_manager_secret_version.aws_metrics_credentials.secret_data).aws_access_key_id
    AWS_SECRET_ACCESS_KEY           = jsondecode(data.google_secret_manager_secret_version.aws_metrics_credentials.secret_data).aws_secret_access_key
    CONFIG_CONTAINER                = var.config_container
    DAILY_REPORT_ENABLED            = var.daily_report_enabled
    DB_HOST                         = local.db_instance_private_ip
    DB_NAME                         = var.db_name
    DB_PORT                         = var.db_port
    DB_USER                         = var.db_user
    DEFAULT_FROM_EMAIL              = local.from_email
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
    MAPPING_FEATURES_V2             = var.mapping_features_v2
    PATROL_ENABLED                  = var.patrol_enabled
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
    TRACK_LENGTH                    = var.track_length
    USE_AZURE_STORAGE               = var.use_azure_storage
    WEB_SERVICE_NAME                = var.web_service_name
    GA_MEASUREMENT_ID               = jsondecode(data.google_secret_manager_secret_version.ga_measurement_id.secret_data).ga_measurement_id
  }
}
