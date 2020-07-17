data "terraform_remote_state" "site_terraform" {
  backend   = "gcs"
  workspace = var.kubernetes_namespace
  config = {
     bucket = "das-terraform-state-0625d0da"
  }
}
