resource "template_dir" "deployments" {
  source_dir      = "${path.root}/templated_deployments"
  destination_dir = "${path.root}/rendered_deployments"
  vars = {
    NAMESPACE = "${yamldecode(file("${path.root}/../ci/params/circleci.params.yaml"))["namespace"]}"
    SERVER_VERSION = "server-version"
  }
}
