provider "google" {
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}

provider "vault" {
  address         = "https://vault.vulcancloud.io:8200"
  skip_tls_verify = "true"
  version         = ">= 2.1"
}

provider "kubernetes" {
  version = "~> 1.10"

  cluster_ca_certificate = base64decode(local.b64_encoded_cluster_or_proxy_ca_certificate)
  host                   = "https://${local.cluster_or_proxy_k8s_endpoint}"
  load_config_file       = false
  token                  = data.google_client_config.k8s.access_token
}
