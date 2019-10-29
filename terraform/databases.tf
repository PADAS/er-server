locals {
  psql_bootstrapping_executor = <<EOF
sudo docker run --rm --interactive --env=PGSSLMODE=require --env=PGPASSWORD=${data.vault_generic_secret.db_password.data["value"]} \
--mount=type=bind,source=$PWD/postgres_bootstrapping.sql,destination=/tmp/postgres_bootstrapping.sql,readonly postgres:9.6 \
psql --host=172.20.0.2 --username=postgres --dbname=${google_sql_database.database.name} --file=/tmp/postgres_bootstrapping.sql \
--variable=db_owner=${google_sql_database.database.name} --variable=db_passwd=${data.vault_generic_secret.db_password.data["value"]} \
--variable=db_name=${google_sql_database.database.name} --single-transaction --variable=ON_ERROR_STOP=1
EOF
}

data "vault_generic_secret" "db_password" {
  path = "padas-app/main/earthranger-app-infra-postgres-server-${terraform.workspace}"
}

resource "google_sql_database" "database" {
  name = "${var.site}_dasdb"
  instance = data.terraform_remote_state.earthranger_app_infra.outputs.db_instance_name

  provisioner "remote-exec" {
        connection {
          host        = google_compute_instance.bastion_server.network_interface.0.access_config.0.nat_ip
          port        = "22"
          private_key = "${tls_private_key.bastion_server.private_key_pem}"
          type        = "ssh"
          user        = "bastion_server"
        }

     inline = [
      local.psql_bootstrapping_executor,
      ]
    }
}

