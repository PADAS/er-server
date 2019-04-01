provider "template" {
  version = "~> 2.0"
}

data "terraform_remote_state" "deployment_infrastructure" {
  backend = "gcs"

  config {
    bucket = "das-backend-beb61125"
    prefix = "deployment-infrastructure"
  }
}

resource "template_dir" "this" {
  source_dir      = "${path.cwd}/deployment"
  destination_dir = "${path.cwd}/rendered"

  vars = {
    apn_db_server_fqdn = "${data.terraform_remote_state.deployment_infrastructure.apn_db_server_fqdn}"
    apn_db_server_name = "${data.terraform_remote_state.deployment_infrastructure.apn_db_server_name}"
    akegera_db_login_password_vault_path = "${data.terraform_remote_state.deployment_infrastructure.akegera_db_login_password_vault_path}"
    akegera_db_name = "${data.terraform_remote_state.deployment_infrastructure.akegera_db_name}"
    akegera_dns_name = "${data.terraform_remote_state.deployment_infrastructure.akegera_dns_name}"
    akegera_public_ip_address = "${data.terraform_remote_state.deployment_infrastructure.akegera_public_ip_address}"
    akegera_storage_account_name = "${data.terraform_remote_state.deployment_infrastructure.akegera_storage_account_name}"
    akegera_storage_account_primary_access_key_vault_path = "${data.terraform_remote_state.deployment_infrastructure.akegera_storage_account_primary_access_key_vault_path}"
    akegera_storage_container_name = "${data.terraform_remote_state.deployment_infrastructure.akegera_storage_container_name}"
    apn_db_server_administrator_login_password_vault_path = "${data.terraform_remote_state.deployment_infrastructure.apn_db_server_administrator_login_password_vault_path}"
    apn_db_server_fqdn = "${data.terraform_remote_state.deployment_infrastructure.apn_db_server_fqdn}"
    apn_db_server_name = "${data.terraform_remote_state.deployment_infrastructure.apn_db_server_name}"
    bangweulu_db_login_password_vault_path = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_db_login_password_vault_path}"
    bangweulu_db_name = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_db_name}"
    bangweulu_dns_name = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_dns_name}"
    bangweulu_public_ip_address = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_public_ip_address}"
    bangweulu_storage_account_name = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_storage_account_name}"
    bangweulu_storage_account_primary_access_key_vault_path = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_storage_account_primary_access_key_vault_path}"
    bangweulu_storage_container_name = "${data.terraform_remote_state.deployment_infrastructure.bangweulu_storage_container_name}"
    liwonde_db_login_password_vault_path = "${data.terraform_remote_state.deployment_infrastructure.liwonde_db_login_password_vault_path}"
    liwonde_db_name = "${data.terraform_remote_state.deployment_infrastructure.liwonde_db_name}"
    liwonde_dns_name = "${data.terraform_remote_state.deployment_infrastructure.liwonde_dns_name}"
    liwonde_public_ip_address = "${data.terraform_remote_state.deployment_infrastructure.liwonde_public_ip_address}"
    liwonde_storage_account_name = "${data.terraform_remote_state.deployment_infrastructure.liwonde_storage_account_name}"
    liwonde_storage_account_primary_access_key_vault_path = "${data.terraform_remote_state.deployment_infrastructure.liwonde_storage_account_primary_access_key_vault_path}"
    liwonde_storage_container_name = "${data.terraform_remote_state.deployment_infrastructure.liwonde_storage_container_name}"
    majete_db_login_password_vault_path = "${data.terraform_remote_state.deployment_infrastructure.majete_db_login_password_vault_path}"
    majete_db_name = "${data.terraform_remote_state.deployment_infrastructure.majete_db_name}"
    majete_dns_name = "${data.terraform_remote_state.deployment_infrastructure.majete_dns_name}"
    majete_public_ip_address = "${data.terraform_remote_state.deployment_infrastructure.majete_public_ip_address}"
    majete_storage_account_name = "${data.terraform_remote_state.deployment_infrastructure.majete_storage_account_name}"
    majete_storage_account_primary_access_key_vault_path = "${data.terraform_remote_state.deployment_infrastructure.majete_storage_account_primary_access_key_vault_path}"
    majete_storage_container_name = "${data.terraform_remote_state.deployment_infrastructure.majete_storage_container_name}"
  }

}
