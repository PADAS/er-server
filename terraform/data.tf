data "google_project" "earthranger" {
  project_id = "earthranger-78ca55ca"
}

data "vault_generic_secret" "alerts_slack_url" {
  path = "${local.legacy_vault_path}/slack-webhook-url-alertmanager"
}

data "vault_generic_secret" "email_username" {
  path = "${local.legacy_vault_path}/email-username"
}

data "vault_generic_secret" "email_password" {
  path = "${local.legacy_vault_path}/email-password"
}

data "vault_generic_secret" "ssl_privatekey_pem" {
  path = var.ssl_privatekey_vault_path
}

data "vault_generic_secret" "ssl_certificate_chain" {
  path = var.ssl_cert_bundle_vault_path
}
