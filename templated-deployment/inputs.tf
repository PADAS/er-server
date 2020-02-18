variable "app_infra_workspace" {
  type = string
}

variable "kubernetes_namespace" {
  type = string
}

variable "site_ip_address" {
  type = string
}

variable "INGRESS_VERSION" {
  type = string
}

variable "SERVER_VERSION" {
  type = string
}

variable "WEB_VERSION" {
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

variable "fqdn" {
  type    = "string"
  default = "localhost"
}

variable "from_email" {
  type    = string
  default = "notifications.demo@pamdas.org"
}


variable "kml_export" {
  type    = string
  default = "true"
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

