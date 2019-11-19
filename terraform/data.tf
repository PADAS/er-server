data "google_project" "earthranger" {
  project_id = "earthranger-78ca55ca"
}

data "vault_generic_secret" "alerts_slack_url" {
  path = "${local.legacy_vault_path}/slack-webhook-url-alertmanager"
}
