resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templated_deployments"
  destination_dir = "${path.root}/rendered_deployments"
  vars = {
    NAMESPACE = var.namespace
    DB_HOST = "${var.namespace}.svc.cluster.local"
    DB_PORT = var.db_port
    DB_NAME = var.db_name
    USE_AZURE_STORAGE = var.use_azure_storage
    STORAGE_CONTAINER = var.storage_container
    KML_EXPORT = var.kml_export
    DEFAULT_FROM_EMAIL = var.default_from_email
    FROM_EMAIL = var.from_email
    EMAIL_HOST = var.email_host
    CONFIG_CONTAINER = var.config_container
  }
}
