provider "google" {
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}

provider "google" {
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
  alias   = "gsm"
  version = "3.79.0"
}

provider "google" {
  alias   = "k8s_cluster"

  project = data.terraform_remote_state.earthranger_app_infra.outputs.cluster_project_id
  scopes = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
  ]
}

provider "google-beta" {
}
provider "kubernetes" {

  cluster_ca_certificate = base64decode(local.b64_encoded_cluster_or_proxy_ca_certificate)
  host                   = "https://${local.cluster_or_proxy_k8s_endpoint}"
  load_config_file       = false
  token                  = data.google_client_config.k8s.access_token
}

provider "aws" {
  version    = "~>2.44"
  access_key = var.access_key
  secret_key = var.secret_key
  region     = "us-east-1"
}
