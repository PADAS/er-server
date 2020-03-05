data "terraform_remote_state" "earthranger_app_infra" {
  backend   = "gcs"
  workspace = var.app_infra_workspace
  config = {
    bucket = "earthranger-app-infra-terraform-state-540d878e"
  }
}

