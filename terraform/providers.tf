provider "google" {
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
  version = ">=2.20"
}

provider "google" {
  version = "~> 2.20"
  alias   = "k8s_cluster"

  project = data.terraform_remote_state.earthranger_app_infra.outputs.cluster_project_id
  scopes = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
  ]
}

provider "google-beta" {
  version = ">=2.19"
}
provider "kubernetes" {
  version = "~> 1.10"

  cluster_ca_certificate = base64decode(local.b64_encoded_cluster_or_proxy_ca_certificate)
  host                   = "https://${local.cluster_or_proxy_k8s_endpoint}"
  load_config_file       = false
  token                  = data.google_client_config.k8s.access_token
}

provider "random" {
  version = ">=2.1"
}

provider "tls" {
  version = ">=2.1"
}

provider "vault" {
  address         = "https://vault.vulcancloud.io:8200"
  skip_tls_verify = "true"
  version         = ">= 2.1"
}

