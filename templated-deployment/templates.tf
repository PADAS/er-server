resource "template_dir" "deployments" {

  source_dir = "${path.root}/templates"

  destination_dir = "${path.root}/rendered"

  vars = {
    API_ENDPOINT         = var.api_endpoint
    API_HOST             = var.api_host
    API_PORT             = var.api_port
    ALERTS_ENABLED       = var.alerts_enabled
    CONFIG_CONTAINER     = var.config_container
    DB_HOST              = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip
    DB_NAME              = var.db_name
    DB_PORT              = var.db_port
    DB_USER              = var.db_user
    DEFAULT_FROM_EMAIL   = var.from_email
    EMAIL_HOST           = var.email_host
    EMAIL_HOST_USER      = var.email_host_user
    FQDN                 = var.fqdn
    FROM_EMAIL           = var.from_email
    GS_BUCKET_NAME       = var.gs_bucket_name
    INGRESS_VERSION      = var.INGRESS_VERSION
    KML_EXPORT           = var.kml_export
    KUBERNETES_NAMESPACE = var.kubernetes_namespace
    SERVER_VERSION       = var.SERVER_VERSION
    MAPPING_FEATURES_V2  = var.mapping_features_v2
    SITE_IP_ADDRESS      = var.site_ip_address
    STORAGE_CONTAINER    = var.storage_container
    TIME_ZONE            = var.time_zone
    USE_AZURE_STORAGE    = var.use_azure_storage
    WEB_SERVICE_NAME     = var.web_service_name
    WEB_VERSION          = var.WEB_VERSION
    ACCEPT_EULA          = var.accept_eula
    ENABLE_DEBUG         = var.enable_debug
    SHOW_TRACK_DAYS      = var.show_track_days
    SHOW_STATIONARY_SUBJECTS_ON_MAP  = var.show_stationary_subjects_on_map
    SMS_ID               = var.sms_id
    SMS_TOKEN            = var.sms_token
    EUS_EMAIL            = var.eus_email
    EUS_NAME             = var.eus_name
    EUS_ORG              = var.eus_org
    EUS_TYPE             = var.eus_type
  }
}
