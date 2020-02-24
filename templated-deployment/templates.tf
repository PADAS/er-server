resource "template_dir" "deployments" {

  source_dir = "${path.root}/templates"

  destination_dir = "${path.root}/rendered"

  vars = {
    API_ENDPOINT         = var.api_endpoint
    API_HOST             = var.api_host
    API_PORT             = var.api_port
    CONFIG_CONTAINER     = var.config_container
    DB_HOST              = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip
    DB_NAME              = var.db_name
    DB_PORT              = var.db_port
    DB_USER              = var.db_user
    DEFAULT_FROM_EMAIL   = var.from_email
    EMAIL_HOST           = var.email_host
    FQDN                 = var.fqdn
    FROM_EMAIL           = var.from_email
    GS_BUCKET_NAME       = var.gs_bucket_name
    INGRESS_VERSION      = var.INGRESS_VERSION
    KML_EXPORT           = var.kml_export
    KUBERNETES_NAMESPACE = var.kubernetes_namespace
    SERVER_VERSION       = var.SERVER_VERSION
    SITE_IP_ADDRESS      = var.site_ip_address
    STORAGE_CONTAINER    = var.storage_container
    TIME_ZONE            = var.time_zone
    USE_AZURE_STORAGE    = var.use_azure_storage
    WEB_SERVICE_NAME     = var.web_service_name
    WEB_VERSION          = var.WEB_VERSION
    ACCEPT_EULA          = var.accept_eula
    ENABLE_DEBUG         = var.enable_debug
    SHOW_TRACK_DAYS      = var.show_track_days
    SMS_ID               = var.sms_id
    SMS_TOKEN            = var.sms_token
  }
}
