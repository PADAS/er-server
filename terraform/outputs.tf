output "gcloud_kubectl_configuration" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.gcloud_kubectl_configuration
}

output "cluster_b64_encoded_proxy_ca_certificate" {
 value = data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate
}

output "cluster_proxy_endpoint" {
 value  = data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint
}
