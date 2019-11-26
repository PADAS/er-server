output "gcloud_kubectl_configuration" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
}
