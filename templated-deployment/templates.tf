resource "template_dir" "deployments" {
  source_dir = "${path.root}/templates"
  # Point this at the deployments path for vcloud
  destination_dir = "${path.root}/rendered"
  vars = {
    API_ENDPOINT         = var.api_endpoint
    API_HOST             = var.api_host
    API_PORT             = var.api_port
    CONFIG_CONTAINER     = var.config_container
    DB_HOST              = local.db_host
    DB_PORT              = var.db_port
    DB_NAME              = var.db_name
    DEFAULT_FROM_EMAIL   = var.from_email
    EMAIL_HOST           = var.email_host
    FROM_EMAIL           = var.from_email
    KML_EXPORT           = var.kml_export
    STORAGE_CONTAINER    = var.storage_container
    USE_AZURE_STORAGE    = var.use_azure_storage
    WEB_SERVICE_NAME     = var.web_service_name
    KUBERNETES_NAMESPACE = var.kubernetes_namespace
    SERVER_VERSION       = var.SERVER_VERSION
    WEB_VERSION          = var.WEB_VERSION
  }
}
