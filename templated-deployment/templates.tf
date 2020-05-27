locals {
  domain_parts = regex("(?P<subdomain>[^.]+).(?P<primary_domain>.*)", var.fqdn)
  standard_from_email = join("", ["notifications.", local.domain_parts["subdomain"],
  "@", local.domain_parts["primary_domain"]])

  from_email                = coalesce(var.from_email, local.standard_from_email)
  resolved_eus_organization = coalesce(var.eus_org, var.fqdn)
}

resource "template_dir" "deployments" {

  source_dir = "${path.root}/templates"

  destination_dir = "${path.root}/rendered"

  vars = {
    ACCEPT_EULA                     = var.accept_eula
    ALERTS_ENABLED                  = var.alerts_enabled
    API_ENDPOINT                    = var.api_endpoint
    API_HOST                        = var.api_host
    API_PORT                        = var.api_port
    AWS_ACCESS_KEY_ID               = data.vault_generic_secret.aws_metrics_credentials.data.aws_access_key_id
    AWS_SECRET_ACCESS_KEY           = data.vault_generic_secret.aws_metrics_credentials.data.aws_secret_access_key
    CONFIG_CONTAINER                = var.config_container
    DAILY_REPORT_ENABLED            = var.daily_report_enabled
    DB_HOST                         = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip
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
    FQDN                            = var.fqdn
    FROM_EMAIL                      = local.from_email
    GFW_CLUSTER_RADIUS              = var.gfw_cluster_radius
    GS_BUCKET_NAME                  = var.gs_bucket_name
    INGRESS_VERSION                 = var.INGRESS_VERSION
    KML_EXPORT                      = var.kml_export
    KUBERNETES_NAMESPACE            = var.kubernetes_namespace
    MAPPING_FEATURES_V2             = var.mapping_features_v2
    SERVER_VERSION                  = var.SERVER_VERSION
    SHOW_STATIONARY_SUBJECTS_ON_MAP = var.show_stationary_subjects_on_map
    SHOW_TRACK_DAYS                 = var.show_track_days
    SITE_IP_ADDRESS                 = var.site_ip_address
    SMS_ID                          = var.sms_id
    SMS_TOKEN                       = var.sms_token
    STORAGE_CONTAINER               = var.storage_container
    TIME_ZONE                       = var.time_zone
    USE_AZURE_STORAGE               = var.use_azure_storage
    WEB_SERVICE_NAME                = var.web_service_name
    WEB_VERSION                     = var.WEB_VERSION
  }
}
