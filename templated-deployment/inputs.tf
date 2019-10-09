variable "api_host" {
  type = string
  default = "api"
}

variable "api_port" {
  type = string
  default = "8000"
}

variable "config_container" {
  type = string
  default = "dev-az"
}

variable "db_name" {
  type = string
  default = "das"
}

variable "db_port" {
  type = string
  default = "5432"
}

variable "kml_export" {
  type = string
  default = "true"
}

variable "storage_container" {
  type = string
  default = ""
}

variable "use_azure_storage" {
  type = string
  default = "false"
}



