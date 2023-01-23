locals {

  db_instances = [
    {
      db_instance            = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name,
      db_instance_private_ip = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_private_ip,
      db_password_path       = "earthranger_app_infra_postgres_server_${local.db_secret_path}"
    },
    {
      db_instance            = local.db_instance_index == 1 ? data.terraform_remote_state.earthranger_app_infra.outputs.db2_instance_name : "",
      db_instance_private_ip = local.db_instance_index == 1 ? data.terraform_remote_state.earthranger_app_infra.outputs.db2_instance_private_ip : "",
      db_password_path       = local.db_instance_index == 1 ? "earthranger_app_infra_postgres_server2_${local.db_secret_path}" : ""
    },
    {
      db_instance            = terraform.workspace == "kws" ? data.terraform_remote_state.earthranger_app_infra.outputs.kws_instance_name : "",
      db_instance_private_ip = terraform.workspace == "kws" ? data.terraform_remote_state.earthranger_app_infra.outputs.kws_instance_private_ip : "",
      db_password_path       = terraform.workspace == "kws" ? "earthranger_app_infra_postgres_kws_${local.db_secret_path}" : ""
    }
  ]

  db_secret_path = data.terraform_remote_state.earthranger_app_infra.outputs.db_secret_path

  sanitized_db_name      = lower(substr(replace(terraform.workspace, "/[^A-Za-z0-9_]/", "_"), 0, 24))
  unique_db_name         = "${local.sanitized_db_name}_${random_string.db_name_uniqueness.result}"
  app_role_name          = "${local.unique_db_name}_approle"
  app_user_name          = "${local.unique_db_name}_appuser"
  db_instance            = element(local.db_instances, local.db_instance_index).db_instance
  db_instance_private_ip = element(local.db_instances, local.db_instance_index).db_instance_private_ip
  db_password_gsm_id     = replace(element(local.db_instances, local.db_instance_index).db_password_path, "/[^A-Za-z0-9_]/", "_")
  migration_role_name    = "${local.unique_db_name}_migrationrole"
  migration_user_name    = "${local.unique_db_name}_migrationuser"

  analytics_role_name = "${local.unique_db_name}_analyticsrole"
  analytics_user_name = "${local.unique_db_name}_analyticsuser"

  pgb_credentials_topic = {
    "prod1"     = var.pgb_credentials_topic_prod_1
    "prod-asia" = var.pgb_credentials_topic_prod_asia
    "dev"       = var.pgb_credentials_topic_dev
  }
  er_reporting_credentials_cfsa = {
    "prod1"     = var.er_reporting_cfsa_credentials_prod1
    "prod-asia" = var.er_reporting_cfsa_credentials_prod_asia
    "dev"       = var.er_reporting_cfsa_credentials_dev
  }
}

resource "random_string" "db_name_uniqueness" {
  length  = 4
  special = false
  upper   = false
}

data "google_secret_manager_secret_version" "db_password" {
  project = data.google_project.earthranger.project_id
  secret  = local.db_password_gsm_id
}

data "google_secret_manager_secret_version" "secret_manager_key" {
  project = data.google_project.earthranger.project_id
  secret  = "secret_manager_key"
}

resource "google_sql_database" "database" {
  project  = data.google_project.earthranger.project_id
  name     = "${local.sanitized_db_name}_${random_string.db_name_uniqueness.result}"
  instance = local.db_instance

  provisioner "remote-exec" {
    connection {
      host        = google_compute_instance.bastion_server[0].network_interface.0.access_config.0.nat_ip
      port        = "22"
      private_key = tls_private_key.bastion_server.private_key_pem
      type        = "ssh"
      user        = "bastion_server"
    }

    inline = ["((sudo docker run --rm --interactive --env=PGSSLMODE=require --env=PGPASSWORD=${jsondecode(data.google_secret_manager_secret_version.db_password.secret_data)["value"]} --mount=type=bind,source=$PWD/postgres_bootstrapping.sql,destination=/tmp/postgres_bootstrapping.sql,readonly postgres:9.6 psql --host=${local.db_instance_private_ip} --username=postgres --dbname=${google_sql_database.database.name} --file=/tmp/postgres_bootstrapping.sql --variable=db_name=${google_sql_database.database.name} --variable=migration_role_name=${local.migration_role_name} --variable=migration_user_name=${local.migration_user_name} --variable=app_role_name=${local.app_role_name} --variable=app_user_name=${local.app_user_name} --variable=analytics_role_name=${local.analytics_role_name} --variable=analytics_user_name=${local.analytics_user_name} --single-transaction --variable=ON_ERROR_STOP=1) && sudo rm -rf /tmp/terraform* && exit 0) || (sudo rm -rf /tmp/terraform* && exit 1)", ]
  }
  depends_on = [
    google_sql_user.migration_role,
    google_sql_user.migration_user,
    google_sql_user.app_role,
    google_sql_user.app_user,
    google_sql_user.analytics_role,
    google_sql_user.analytics_user
  ]

}

# Migration Role and User
resource "random_password" "migration_role_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "migration_role" {
  project  = data.google_project.earthranger.project_id
  name     = local.migration_role_name
  instance = local.db_instance
  password = random_password.migration_role_pass.result
}

resource "random_password" "migration_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "migration_user" {
  project  = data.google_project.earthranger.project_id
  name     = local.migration_user_name
  instance = local.db_instance
  password = random_password.migration_user_pass.result
}


# Analytics Role and User
resource "random_password" "analytics_role_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "analytics_role" {
  project  = data.google_project.earthranger.project_id
  name     = local.analytics_role_name
  instance = local.db_instance
  password = random_password.analytics_role_pass.result
}

resource "random_password" "analytics_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "analytics_user" {
  project  = data.google_project.earthranger.project_id
  name     = local.analytics_user_name
  instance = local.db_instance
  password = random_password.analytics_user_pass.result
}

# App Role and User
resource "random_password" "app_role_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "app_role" {
  project  = data.google_project.earthranger.project_id
  name     = local.app_role_name
  instance = local.db_instance
  password = random_password.app_role_pass.result
}

resource "random_password" "app_user_pass" {
  length           = 12
  min_lower        = 2
  min_special      = 2
  min_upper        = 2
  special          = true
  override_special = "_%@"
}

resource "google_sql_user" "app_user" {
  project  = data.google_project.earthranger.project_id
  name     = local.app_user_name
  instance = local.db_instance
  password = random_password.app_user_pass.result

  depends_on = [
    random_password.app_user_pass
  ]
}

resource "google_secret_manager_secret" "er_sql_analytics_info" {
  secret_id = "er_${local.sanitized_db_name}_sql_analytics_info"
  project   = data.google_project.earthranger.project_id

  labels = {
    app         = "earthranger"
    consumer    = "tableau_bi_api"
    environment = local.kubernetes_cluster_name
  }
  replication {
    automatic = true
  }
  topics {
    name = local.pgb_credentials_topic[local.kubernetes_cluster_name]
  }
  # rotation block is needed to add topics
  rotation {}
}

resource "google_secret_manager_secret_version" "secret-version-basic" {
  secret = google_secret_manager_secret.er_sql_analytics_info.id

  secret_data = jsonencode({
    "user"        = google_sql_user.analytics_user.name
    "password"    = random_password.analytics_user_pass.result
    "db_host"     = local.db_instance_private_ip
    "db_name"     = local.unique_db_name
    "environment" = local.kubernetes_cluster_name
  })
}

# Grants cloud build identity on earthranger-tools project access to *_sql_analytics_info secret
resource "google_secret_manager_secret_iam_member" "ertools_cloud_build_secret_accesor" {
  project   = data.google_project.earthranger.project_id
  role      = "roles/secretmanager.secretAccessor"
  secret_id = google_secret_manager_secret.er_sql_analytics_info.id
  member    = "serviceAccount:${var.ertools_cloud_build_identity}"
}

resource "google_secret_manager_secret_iam_member" "ertools_cloud_build_secret_viewer" {
  project   = data.google_project.earthranger.project_id
  role      = "roles/secretmanager.viewer"
  secret_id = google_secret_manager_secret.er_sql_analytics_info.id
  member    = "serviceAccount:${var.ertools_cloud_build_identity}"
}

resource "google_secret_manager_secret_iam_member" "er_reporting_credentials_cfsa_secret_accesor" {
  project   = data.google_project.earthranger.project_id
  role      = "roles/secretmanager.secretAccessor"
  secret_id = google_secret_manager_secret.er_sql_analytics_info.id
  member    = "serviceAccount:${local.er_reporting_credentials_cfsa[local.kubernetes_cluster_name]}"
}

resource "google_secret_manager_secret_iam_member" "er_reporting_credentials_cfsa_secret_viewer" {
  project   = data.google_project.earthranger.project_id
  role      = "roles/secretmanager.viewer"
  secret_id = google_secret_manager_secret.er_sql_analytics_info.id
  member    = "serviceAccount:${local.er_reporting_credentials_cfsa[local.kubernetes_cluster_name]}"
}
