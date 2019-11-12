resource "kubernetes_namespace" "this" {
  metadata {
    name = terraform.workspace
  }
}
