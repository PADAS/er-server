provider "google" {
  project = "earthranger-78ca55ca"
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}

