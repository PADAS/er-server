output "gcloud_kubectl_configuration" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.gcloud_kubectl_configuration
}

output "cluster_b64_encoded_proxy_ca_certificate" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate
}

output "cluster_proxy_endpoint" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint
}

output "kubernetes_namespace" {
  value = kubernetes_namespace.this.metadata.0.name
}

output "database_name" {
  value = google_sql_database.database.name
}

output "site_ip_address" {
  value = google_compute_address.site_ip_address.address
}

output "user_uploads_bucket_name" {
  value = google_storage_bucket.user_uploads.name
}
