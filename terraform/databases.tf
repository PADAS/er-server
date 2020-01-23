locals {
  db_secret_path    = (local.is_production ? "prod1" : "dev")
  sanitized_db_name = substr(replace(terraform.workspace, "/[^A-Za-z0-9_]/", "_"), 0, 24)
}

resource "random_string" "db_name_uniqueness" {
  length  = 4
  special = false
}

data "vault_generic_secret" "db_password" {
  path = "padas-app/main/earthranger-app-infra-postgres-server-${local.db_secret_path}"
}

resource "google_sql_database" "database" {
  project  = data.google_project.earthranger.project_id
  name     = "${local.sanitized_db_name}_${random_string.db_name_uniqueness.result}"
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name

  provisioner "remote-exec" {
    connection {
      host        = google_compute_instance.bastion_server[0].network_interface.0.access_config.0.nat_ip
      port        = "22"
      private_key = "${tls_private_key.bastion_server.private_key_pem}"
      type        = "ssh"
      user        = "bastion_server"
    }

    inline = [
      "((sudo docker run --rm --interactive --env=PGSSLMODE=require --env=PGPASSWORD=${data.vault_generic_secret.db_password.data["value"]} --mount=type=bind,source=$PWD/postgres_bootstrapping.sql,destination=/tmp/postgres_bootstrapping.sql,readonly postgres:9.6 psql --host=${data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip} --username=postgres --dbname=${google_sql_database.database.name} --file=/tmp/postgres_bootstrapping.sql --variable=db_owner=${google_sql_database.database.name} --variable=db_passwd=${data.vault_generic_secret.db_password.data["value"]} --variable=db_name=${google_sql_database.database.name} --single-transaction --variable=ON_ERROR_STOP=1) && sudo rm -rf /tmp/terraform* && exit 0) || (sudo rm -rf /tmp/terraform* && exit 1)"
    ]
  }
}

resource "random_password" "sql_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "users" {
  project  = data.google_project.earthranger.project_id
  name     = google_sql_database.database.name
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
  password = random_password.sql_user_pass.result

  depends_on = [
    random_password.sql_user_pass
  ]
}

resource "random_password" "migrations_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}


resource "google_sql_user" "migrations" {
  project  = data.google_project.earthranger.project_id
  name     = "${google_sql_database.database.name}_migrator"
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
  password = random_password.migrations_user_pass.result

  depends_on = [
    random_password.migrations_user_pass

  ]
}



resource "random_password" "analytics_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "analytics" {
  project  = data.google_project.earthranger.project_id
  name     = "${google_sql_database.database.name}_analytics"
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
  password = random_password.analytics_user_pass.result

  depends_on = [
    random_password.analytics_user_pass
  ]
}

resource "random_password" "apps_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "apps" {
  project  = data.google_project.earthranger.project_id
  name     = "${google_sql_database.database.name}_app"
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
  password = random_password.apps_user_pass.result

  depends_on = [
    random_password.apps_user_pass
  ]
}
