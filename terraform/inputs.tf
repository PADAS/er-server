variable "namespace" {
  type = string
  default = "default"
}

variable "db_port" {
  type = string
  default = "5432"
}

variable "db_name" {
  type = string
  default = "das"
}

variable "db_user" {
  type = string
  default = "das"
}

variable "use_azure_storage" {
  type = string
  default = "false"
}
