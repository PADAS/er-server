resource "kubernetes_namespace" "this" {
  metadata {
    # To be DNS compliant, replace _ with -
    name = replace(terraform.workspace, "_", "-")
  }
}
