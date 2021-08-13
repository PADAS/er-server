variable "firewall_priority_threshold" {
  description = "For historical reasons. vCloud has provisioned many GCP projects with default networks with a default-deny-all set at 900."
  type        = string
  default     = "900"
}

variable "is_running_in_automation" {
  type    = bool
  default = false
}

data "google_client_config" "k8s" {
  provider = google.k8s_cluster
}

variable "need_bastion_server" {
  description = "Only set to true when postgres bootstrapping is necessary. Meant to be short lived, make sure to revert to false, so that a bastion server with a public IP does not persist."
  type        = bool
  default     = false
}

variable "aws_region" {
  type        = string
  description = "AWS region to perform operations from."
  default     = "us-east-1"
}
variable "secret_key" {
  type        = string
  description = "AWS secret key"
  default     = ""
}

variable "access_key" {
  type        = string
  description = "AWS access key Id"
  default     = ""
}

data "aws_route53_zone" "public" {
  name = "pamdas.org."
}

variable "subdomain_name" {
  type        = string
  description = "Subdomain to create in Route53"
  default     = null
}

variable "ssl_privatekey_gsm_id" {
  type        = string
  description = "GSM ID for SSL private key"
  default     = "generic_privatekey_pem"
}

variable "ssl_certificate_gsm_id" {
  type        = string
  description = "GSM ID for SSL private key"
  default     = "generic_fullchain_pem"
}

variable "versioning_enabled" {
  description = "If true then versioning is enabled for all objects in this bucket."
  default     = "true"
}
