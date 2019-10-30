variable "site" {
  description = "Name of site, used for naming resources and dns"
  type        = string
  default     = "dev"
}

variable "bastion_server_count" {
  type    = string
  default = "1"
}

variable "firewall_priority_threshold" {
  description = "For historical reasons. vCloud has provisioned many GCP projects with default networks with a default-deny-all set at 900."
  type        = string
  default     = "900"
}

