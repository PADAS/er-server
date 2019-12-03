locals  {
  db_host = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip 

  this_workspaces_to_infra_workspaces = {
    # if not here, the lookup has a default
  }

  default_infra_workspace_when_not_mapped_here = "dev"
}

variable "api_endpoint" {
  type = string
  default = "localhost"
}

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

variable "web_service_name" {
  type = string
  default = "web"
}



