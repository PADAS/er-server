data "terraform_remote_state" "earthranger_app_infra" {
  backend   = "gcs"
  workspace = local.kubernetes_cluster_name
  config = {
    bucket = "earthranger-app-infra-terraform-state-540d878e"
  }
}

data "terraform_remote_state" "terraform_gcp" {
  backend = "gcs"
  # There is only a single terraform_gcp workspace
  workspace = "default"
  config = {
    bucket = "terraform-gcp-terraform-state-8c148386"
  }
}

