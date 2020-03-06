resource "kubernetes_namespace" "this" {
  metadata {
    # To be DNS compliant, replace _ with -
    name = lower(replace(terraform.workspace, "/([[:punct:]]|_)/" , "-"))
  }
}
