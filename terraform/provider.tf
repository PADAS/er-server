provider "google" {
  project = "earthranger-78ca55ca"
  region  = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_region
}

provider "vault" {
  skip_tls_verify = "true"
  version         = ">= 2.1"
}

provider "tls" {
  version    = ">= 2.0"
}

provider "google-beta" {
  version = ">= 2.11"
}
