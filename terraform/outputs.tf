output "gcloud_kubectl_configuration" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.gcloud_kubectl_configuration
}

output "cluster_name" {
  # replace with data.terraform_remote_state.earthranger_app_infra.outputs.cluster_name
  value = regex("gcloud container clusters get-credentials (?P<cluster_name>\\S+) --zone", data.terraform_remote_state.earthranger_app_infra.outputs.gcloud_kubectl_configuration).cluster_name
}

output "cluster_b64_encoded_proxy_ca_certificate" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.b64_encoded_proxy_ca_certificate
}

output "cluster_proxy_endpoint" {
  value = data.terraform_remote_state.earthranger_app_infra.outputs.proxy_endpoint
}

output "app_infra_workspace" {
  value = data.terraform_remote_state.earthranger_app_infra.workspace
}

output "kubernetes_namespace" {
  value = kubernetes_namespace.this.metadata.0.name
}

output "fqdn" {
  value = aws_route53_record.www.name
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

output "migration_user_name" {
  value = google_sql_user.migration_user.name
}

output "migration_user_pass" {
  value     = google_sql_user.migration_user.password
  sensitive = true
}

output "app_user_name" {
  value = google_sql_user.app_user.name
}

output "app_user_pass" {
  value = google_sql_user.app_user.password
  #sensitive = true
}

output "analytics_user_name" {
  value = google_sql_user.analytics_user.name
}

output "analytics_user_pass" {
  value     = google_sql_user.analytics_user.password
  sensitive = true
}

output "db_instance_private_ip" {
  value     = local.db_instance_private_ip
}
