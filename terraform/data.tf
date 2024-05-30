data "google_project" "earthranger" {
  project_id = "earthranger-78ca55ca"
}

data "google_secret_manager_secret_version" "alerts_slack_url" {
  project = data.google_project.earthranger.project_id
  secret  = "slack_webhook_url_alertmanager"
}

data "google_secret_manager_secret_version" "email_username" {
  project = data.google_project.earthranger.project_id
  secret  = "email_username"
}

data "google_secret_manager_secret_version" "email_password" {
  project = data.google_project.earthranger.project_id
  secret  = "email_password"
}

data "google_secret_manager_secret_version" "ssl_privatekey_pem" {
  project = data.google_project.earthranger.project_id
  secret  = var.ssl_privatekey_gsm_id
}

data "google_secret_manager_secret_version" "ssl_certificate_chain" {
  project = data.google_project.earthranger.project_id
  secret  = var.ssl_certificate_gsm_id
}

data "google_secret_manager_secret_version" "twilio_account_settings" {
  project = data.google_project.earthranger.project_id
  secret  = "twilio_default"
}

data "google_secret_manager_secret_version" "ubi_api_credentials" {
  project = data.google_project.earthranger.project_id
  secret  = "ubi_api_credentials"
}

data "google_secret_manager_secret_version" "kerlink_credentials" {
  project = data.google_project.earthranger.project_id
  secret  = "kerlink_credentials"
}

data "google_secret_manager_secret_version" "tableau_api_credentials" {
  project = data.google_project.earthranger.project_id
  secret  = "tableau_api_credentials"
}

data "google_secret_manager_secret_version" "aws_metrics_credentials" {
  project = data.google_project.earthranger.project_id
  secret  = "aws_metrics_credentials"
}

data "google_secret_manager_secret_version" "ga_measurement_id" {
  project = data.google_project.earthranger.project_id
  secret  = "ga_measurement_id"
}

data "google_secret_manager_secret_version" "tms_dev_api_key" {
  project = data.google_project.earthranger.project_id
  secret  = "tms-dev-api-key"
}

data "google_secret_manager_secret_version" "tms_prod_api_key" {
  project = data.google_project.earthranger.project_id
  secret  = "tms-prod-api-key"
}

data "google_secret_manager_secret_version" "memory_store_prod_api_key" {
  project = data.google_project.earthranger.project_id
  secret  = "memory-store-prod-api-key"
}

data "google_secret_manager_secret_version" "memory_store_dev_api_key" {
  project = data.google_project.earthranger.project_id
  secret  = "memory-store-dev-api-key"
}

data "google_secret_manager_secret_version" "mapbox_token" {
  project = data.google_project.earthranger.project_id
  secret  = "mapbox-token"
}
