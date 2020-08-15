data "terraform_remote_state" "site_terraform" {
  backend   = "gcs"
  workspace = var.site_terraform_workspace
  config = {
     bucket = "das-terraform-state-0625d0da"
  }
}
