data "terraform_remote_state" "earthranger_app_infra" {
  backend = "gcs"
  config = {
    bucket = "earthranger-app-infra-terraform-state-540d878e"
  }
}

