resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templated_deployments"
  destination_dir = "${path.root}/rendered_deployments"
  vars = {
    NAMESPACE = var.namespace
    DB_HOST = "${var.namespace}.svc.cluster.local"
    DB_PORT = var.db_port
    DB_NAME = var.db_name
    DB_USER = var.db_user
    USE_AZURE_STORAGE = var.use_azure_storage
  }
}
