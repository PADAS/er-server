resource "google_sql_database" "database" {
    name = "my-database"
    # instance is set explicitly on the db
    instance = "${data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name}"
}

# Store in vault (pattern in earthranger_app_infra)
resource "random_string" "db_password" {
  length  = 16
  special = true
}

resource "postgresql_role" "db_role" {
  name     = "${var.site}_user"
  login    = true
  password = random_string.db_password.result
}

# Old AWS code
resource "postgresql_database" "db" {
  owner    = postgresql_role.db_role.name
  name     = "${var.site}_dasdb"
  encoding = "UTF8"
}

resource "postgresql_extension" "btree_extension" {
  name = "btree_gist"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "unaccent_extension" {
  name = "unaccent"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "uuid_extension" {
  name = "uuid-ossp"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "postgis_extension" {
  name = "postgis"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "postgis_top_extension" {
  name = "postgis_topology"
  database = "${postgresql_database.db.name}"
  depends_on = [
    postgresql_extension.postgis_extension,
  ]
}

