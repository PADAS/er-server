provider "google" {
  project = "earthranger-78ca55ca"
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}

provider "vault" {
  address         = "https://vault.vulcancloud.io:8200"
  skip_tls_verify = "true"
  version         = ">= 2.1"
}

provider "tls" {
  tls    = ">= 2.0"
}
