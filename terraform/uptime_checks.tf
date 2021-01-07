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

resource "google_monitoring_alert_policy" "ssl_alert_policy" {
  display_name = "SSL certificate expiring soon"
  project      = data.google_project.earthranger.project_id
  combiner     = "OR"
  conditions {
    display_name = "SSL certificate expiring soon"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires\" AND resource.type=\"uptime_url\""
      duration        = "600s"
      threshold_value = 15
      trigger {
        count = 1
      }
      comparison = "COMPARISON_LT"
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields = [
          "resource.label.*"
        ]
      }
    }
  }

  user_labels = {
    uptime  = "ssl_cert_expiration"
    version = "1"
  }

  notification_channels = [
    "projects/earthranger-78ca55ca/notificationChannels/17849266361997779646"
  ]
}

