locals {

  this_workspaces_to_infra_workspaces = {
    # if not here, the lookup has a default
    das4794 = "prod1"
  }

  default_infra_workspace_when_not_mapped_here = "dev"

  b64_encoded_cluster_or_proxy_ca_certificate = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate : data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_cluster_ca_certificate

  cluster_or_proxy_k8s_endpoint = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint : data.terraform_remote_state.earthranger_app_infra.outputs.cluster_endpoint


  legacy_vault_path = "padas-app/main"


}

