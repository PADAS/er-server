resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templated_deployments"
  destination_dir = "${path.root}/rendered_deployments"
  vars = {
    NAMESPACE = "namespace"
    SERVER_VERSION = "server-version"
  }
}
