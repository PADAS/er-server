variable "firewall_priority_threshold" {
  description = "For historical reasons. vCloud has provisioned many GCP projects with default networks with a default-deny-all set at 900."
  type        = string
  default     = "900"
}

variable "is_running_in_automation" {
  type = bool
  default = false
}

data "google_client_config" "k8s" {
  provider = google.k8s_cluster
}

variable "need_bastion_server" {
  description = "Only set to true when postgres bootstrapping is necessary. Meant to be short lived, make sure to revert to false, so that a bastion server with a public IP does not persist."
  type    = bool
  default = false
}


