locals {
  legacy_vault_path = "secret/earthranger/migrated"
}

data "vault_generic_secret" "aws_metrics_credentials" {
  path = "${local.legacy_vault_path}/earthranger/aws_metrics_credentials"
}

data "vault_generic_secret" "ga_measurement_id" {
  path = "secret/earthranger/ga_measurement_id"
}

