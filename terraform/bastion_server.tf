locals {

  bastion_server_count = var.need_bastion_server ? 1 : 0
  bastion_server_user  = "bastion_server"

  # Do not change bastion_tag values: CircleCI relies on them to safelist build agents with a firewall rule,
  # independent of terraform.
  bastion_tag = "psql-bastion"
}

resource "tls_private_key" "bastion_server" {
  algorithm = "RSA"
}

data "google_compute_image" "ubuntu" {
  provider = google

  family  = "ubuntu-pro-1804-lts"
  project = "ubuntu-os-pro-cloud"
}

resource "random_string" "bastion_name_uniqueness" {
  length  = 4
  special = false
  upper   = false
}

resource "google_compute_instance" "bastion_server" {

  timeouts {
    create = "15m"
    update = "15m"
    delete = "15m"
  }

  # Toggle this variable to ensure bastion server spins down after bootstrapping
  count = local.bastion_server_count

  allow_stopping_for_update = "true"
  machine_type              = "g1-small"
  name                      = "psql-bastion-server-${random_string.bastion_name_uniqueness.result}"
  project                   = data.google_project.earthranger.project_id
  zone                      = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_zone
  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
    }
  }

  tags = [local.bastion_tag]

  labels = {
    role      = "psql-bastion-server"
    workspace = lower(terraform.workspace)
  }

  metadata = {
    ssh-keys = "${local.bastion_server_user}:${tls_private_key.bastion_server.public_key_openssh}"
  }

  network_interface {

    subnetwork         = local.subnetwork_name
    subnetwork_project = data.google_project.earthranger.project_id

    access_config { # necessary to allocate public ip
    }
  }

  provisioner "file" {
    source      = "${path.root}/bastion_server_scripts/postgres_bootstrapping.sql"
    destination = "/home/${local.bastion_server_user}/postgres_bootstrapping.sql"

    connection {
      host        = google_compute_instance.bastion_server[0].network_interface.0.access_config.0.nat_ip
      type        = "ssh"
      private_key = tls_private_key.bastion_server.private_key_pem
      user        = local.bastion_server_user
    }
  }

  provisioner "remote-exec" {
    connection {
      host        = google_compute_instance.bastion_server[0].network_interface.0.access_config.0.nat_ip
      port        = "22"
      private_key = tls_private_key.bastion_server.private_key_pem
      type        = "ssh"
      user        = local.bastion_server_user
    }

    script = "${path.root}/bastion_server_scripts/docker_install.sh"

  }

}
