locals {
  is_production        = (data.terraform_remote_state.earthranger_app_infra.workspace == "prod1")
  dev_subnetwork_name  = data.terraform_remote_state.terraform_gcp.outputs.dev_us_west_1_subnetwork_name
  prod_subnetwork_name = data.terraform_remote_state.terraform_gcp.outputs.prod_europe_west_3_subnetwork_name


  dev_network_name  = data.terraform_remote_state.terraform_gcp.outputs.dev_network_name
  prod_network_name = data.terraform_remote_state.terraform_gcp.outputs.prod_network_name

  subnetwork_name = local.is_production ? local.prod_subnetwork_name : local.dev_subnetwork_name
  network_name    = local.is_production ? local.prod_network_name : local.dev_network_name

  this_workspaces_to_infra_workspaces = {
    # if not here, the lookup has a default
    "demo-two" = "prod1"
    "garamba" = "prod1"
    "connected-conservation" = "prod1"
    "chipinge" = "prod1"
    "bubyevalley" = "prod1"
    "mtkenya" = "prod1"
    "ewt" = "prod1"
    "gotcha" = "prod1"
    "marataba" = "prod1"
    "thabatholo" = "prod1"
    "welgevonden" = "prod1"
    "training" = "prod1"
    "biocarbonpartners" = "prod1"
    "bomani" = "prod1"
    "wildhorizons" = "prod1"
    "bangweulu" = "prod1"
  }

  default_infra_workspace_when_not_mapped_here = "dev"

  b64_encoded_cluster_or_proxy_ca_certificate = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate : data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_cluster_ca_certificate

  cluster_or_proxy_k8s_endpoint = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint : data.terraform_remote_state.earthranger_app_infra.outputs.cluster_endpoint


  legacy_vault_path = "padas-app/main"


}

