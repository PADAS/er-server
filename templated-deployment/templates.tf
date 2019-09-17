resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templates"
  # Point this at the deployments path for vcloud
  destination_dir = "${path.root}/rendered"
  vars = {
    NAMESPACE = var.namespace
    DB_HOST = "${var.namespace}.svc.cluster.local"
    DB_PORT = var.db_port
    DB_NAME = var.db_name
    USE_AZURE_STORAGE = var.use_azure_storage
    STORAGE_CONTAINER = var.storage_container
    KML_EXPORT = var.kml_export
    CONFIG_CONTAINER = var.config_container
  }
}
