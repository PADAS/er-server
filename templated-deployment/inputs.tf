variable "app_infra_workspace" {
  type = string
}

variable "site_terraform_workspace" {
  type = string
}

variable "kubernetes_namespace" {
  type = string
}

variable "site_ip_address" {
  type = string
}

variable "time_zone" {
  type    = string
  default = "US/Pacific"
}

variable "INGRESS_VERSION" {
  type = string
}

variable "SERVER_VERSION" {
  type = string
}

variable "WEB_REACT_VERSION" {
  type = string
}

variable "WEB_ADMIN_VERSION" {
  type = string
}

variable "api_endpoint" {
  type    = string
  default = "localhost"
}

variable "api_host" {
  type    = string
  default = "api"
}

variable "api_port" {
  type    = string
  default = "8000"
}

variable "config_container" {
  type    = string
  default = "dev-az"
}

variable "db_user" {
  type    = string
  default = "postgres"
}

variable "db_name" {
  type = string
}

variable "db_port" {
  type    = string
  default = "5432"
}

variable "gs_bucket_name" {
  type    = string
  default = "earthranger-uploads-default"
}

variable "email_host" {
  type    = string
  default = "email-smtp.us-west-2.amazonaws.com"
}

variable "feature_tms" {
  description = "Enable feature tms flag"
  type        = string
  default     = "False"
}

variable "fqdn" {
  type    = string
  default = "localhost"
}

variable "from_email" {
  type    = string
  default = null
}

variable "kml_export" {
  type    = string
  default = "true"
}

variable "kml_feed_title" {
  type    = string
  default = "EarthRanger KML Service"
}

variable "kml_overlay_image" {
  type    = string
  default = null
}

variable "storage_container" {
  type    = string
  default = ""
}

variable "use_azure_storage" {
  type    = string
  default = "false"
}

variable "web_service_name" {
  type    = string
  default = "web"
}
variable "accept_eula" {
  type    = string
  default = "true"
}
variable "gfw_cluster_radius" {
  type    = string
  default = "5"
}
variable "gfw_backfill_interval_days" {
  type = string
  default = 10
}
variable "enable_debug" {
  type    = string
  default = "false"
}
variable "show_track_days" {
  type    = string
  default = "16"
}
variable "default_event_filter_from_days" {
  type    = string
  default = "-1"
}
variable "default_patrol_filter_from_days" {
  type    = string
  default = "-1"
}


variable "eus_email" {
  type    = string
  default = ""
}
variable "eus_name" {
  type    = string
  default = ""
}
variable "eus_org" {
  type    = string
  default = null
}

variable "eus_type" {
  type    = string
  default = "email"
}
variable "sms_id" {
  type    = string
  default = ""
}
variable "sms_token" {
  type    = string
  default = ""
}

variable "sendsms_twilio_from_number" {
  type    = string
  default = "+12062033988"
}

variable "daily_report_enabled" {
  type    = string
  default = "False"
}

variable "alerts_enabled" {
  type    = string
  default = "True"
}

variable "alerts_rate_limit" {
  type    = string
  default = "20"
}

variable "email_host_user" {
  type    = string
  default = ""
}
variable "mapping_features_v2" {
  type    = string
  default = "True"
}

variable "show_stationary_subjects_on_map" {
  type    = string
  default = "True"
}

variable "patrol_enabled" {
  type    = string
  default = "True"
}

variable "subject_region_enabled" {
  type    = string
  default = "True"
}

variable "tableau_enabled" {
  type    = string
  default = "False"
}

variable "tableau_site_id" {
  type    = string
  default = ""
}

variable "tableau_default_dashboard" {
  type     = string
  default = "er_standard_analytics/summary"
}

variable "track_length" {
  type    = string
  default = "21"
}

variable "alt_server_names" {
  description = "comma-delimited list of alternative server names, to be used for ALLOWED_HOSTS and CORS."
  type    = list(string)
  default = []
}

variable "geo_permission_speed_km_h" {
  description = "Speed in km/h for geo permissions"
  type        = string
  default     = "75"
}

variable "tms_api_host" {
  description = "tms api host"
  type        = string
  default     = "https://er-tms-api-gateway-5sf422kw.uc.gateway.dev"
}

variable "tms_api_key" {
  description = "tms api key"
  type        = string
  default     = ""
}

variable "root_logging_level" {
  type        = string
  default     = "WARNING"
}

variable "django_logging_level" {
  type        = string
  default     = "INFO"
}

variable "django_request_logging_level" {
  type        = string
  default     = "INFO"
}

variable "django_server_logging_level" {
  type        = string
  default     = "INFO"
}

variable "rtapi_logging_level" {
  type        = string
  default     = "WARNING"
}

variable "rtapi_socket_logging_level" {
  type        = string
  default     = "WARNING"
}

variable "rtapi_pubsub_logging_level" {
  type        = string
  default     = "WARNING"
}

variable "memory_store_host" {
  description = "memory store host"
  type        = string
  default     = "34.82.41.46"
}

variable "memory_store_database" {
  description = "memory store database"
  type        = string
  default     = "0"
}

variable "memory_store_api_key" {
  description = "memory store password"
  type        = string
  default     = ""
}

variable "memory_store_port" {
  description = "memory store port"
  type        = string
  default     = ""
}

variable "mapbox_token" {
  type    = string
  default = ""
}
