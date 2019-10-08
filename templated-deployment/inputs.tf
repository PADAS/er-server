variable "api_host" {
  type = string
  default = "api"
}

variable "api_port" {
  type = string
  default = "8000"
}

variable "db_port" {
  type = string
  default = "5432"
}

variable "db_name" {
  type = string
  default = "das"
}

variable "use_azure_storage" {
  type = string
  default = "false"
}

variable "storage_container" {
  type = string
  default = ""
}

variable "kml_export" {
  type = string
  default = "true"
}

variable "config_container" {
  type = string
  default = "dev-az"
}
