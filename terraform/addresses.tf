resource "google_compute_address" "site_ip_address" {
  provider = google

  name    = "site-ip-${terraform.workspace}"
  project = data.terraform_remote_state.earthranger_app_infra.outputs.cluster_project_id
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}
