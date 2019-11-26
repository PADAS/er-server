output "gcloud_kubectl_configuration" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.gcloud_kubectl_configuration
}
