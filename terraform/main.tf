resource "google_sql_database" "database" {
  name = "${var.site}_dasdb"
  # instance is set explicitly on the db
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name
}

