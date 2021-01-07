resource "google_monitoring_uptime_check_config" "this" {
  display_name = local.subdomain_name
  timeout      = "15s"
  period       = "60s"
  project      = data.google_project.earthranger.project_id

  http_check {
    path         = "/api/v1.0/status?db_connections=true"
    port         = "443"
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = data.google_project.earthranger.project_id
      host       = "${local.subdomain_name}.pamdas.org"
    }
  }

}
