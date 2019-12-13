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
