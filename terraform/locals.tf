locals {

  subnetwork_name = data.terraform_remote_state.earthranger_app_infra.outputs.subnetwork_name
  network_name    = data.terraform_remote_state.earthranger_app_infra.outputs.network_name

  this_workspaces_to_infra_workspaces = {
    # if not here, the lookup has a default
    "africanparks"           = "prod1"
    "akagera"                = "prod1"
    "amakhala"               = "prod1"
    "balule"                 = "prod1"
    "bangweulu"              = "prod1"
    "biocarbonpartners"      = "prod1"
    "bomani"                 = "prod1"
    "bubyevalley"            = "prod1"
    "chipinge"               = "prod1"
    "connected-conservation" = "prod1"
    "demo-two"               = "prod1"
    "elephantsalive"         = "prod1"
    "ewt"                    = "prod1"
    "garamba"                = "prod1"
    "gonarezhou"             = "prod1"
    "gotcha"                 = "prod1"
    "liwonde"                = "prod1"
    "madikwe"                = "prod1"
    "majete"                 = "prod1"
    "marataba"               = "prod1"
    "matlamamba"             = "prod1"
    "mtkenya"                = "prod1"
    "natgeo"                 = "prod1"
    "nkhotakota"             = "prod1"
    "oljogi"                 = "prod1"
    "sabiegamereserve"       = "prod1"
    "sabisands"              = "prod1"
    "sawc"                   = "prod1"
    "thabatholo"             = "prod1"
    "training"               = "prod1"
    "welgevonden"            = "prod1"
    "wildhorizons"           = "prod1"
    "zakouma"                = "prod1"
    "degrees51"              = "prod1"
    "malamala"               = "prod1"
    "hello-asia"             = "prod-asia"
    "socp"                   = "prod-asia"
    "westernsiempang"        = "prod-asia"
    "damai"                  = "prod-asia"
  }

  default_infra_workspace_when_not_mapped_here = "dev"

  b64_encoded_cluster_or_proxy_ca_certificate = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate : data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_cluster_ca_certificate

  cluster_or_proxy_k8s_endpoint = var.is_running_in_automation ? data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint : data.terraform_remote_state.earthranger_app_infra.outputs.cluster_endpoint


  legacy_vault_path = "padas-app/main"


}

