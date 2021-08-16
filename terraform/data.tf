data "google_project" "earthranger" {
  project_id = "earthranger-78ca55ca"
}

data "google_secret_manager_secret_version" "alerts_slack_url" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "slack_webhook_url_alertmanager"
}

data "google_secret_manager_secret_version" "email_username" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "email_username"
}

data "google_secret_manager_secret_version" "email_password" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "email_password"
}

data "google_secret_manager_secret_version" "ssl_privatekey_pem" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = var.ssl_privatekey_gsm_id
}

data "google_secret_manager_secret_version" "ssl_certificate_chain" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = var.ssl_certificate_gsm_id
}

data "google_secret_manager_secret_version" "twilio_account_settings" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "twilio_default"
}

data "google_secret_manager_secret_version" "ubi_api_credentials" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "ubi_api_credentials"
}

data "google_secret_manager_secret_version" "kerlink_credentials" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "kerlink_credentials"
}

data "google_secret_manager_secret_version" "tableau_api_credentials" {
  provider = "gsm"
  project = data.google_project.earthranger.project_id
  secret  = "tableau_api_credentials"
}
