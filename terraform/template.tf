resource "template_dir" "this" {
  source_dir      = "${path.root}/templated_deployments/components/deployments"
  destination_dir = "${path.root}/rendered_deployments"
  vars = {
    NAMESPACE = "namespace"
    SERVER_VERSION = "server-version"
  }
}
