locals {
  is_production = (terraform.workspace == "prod")
  dev_subnetwork_name = data.terraform_remote_state.terraform_gcp.outputs.dev_us_west_1_subnetwork_name
  prod_subnetwork_name = data.terraform_remote_state.terraform_gcp.outputs.prod_europe_west_3_subnetwork_name


  dev_network_name = data.terraform_remote_state.terraform_gcp.outputs.dev_network_name
  prod_network_name = data.terraform_remote_state.terraform_gcp.outputs.prod_network_name

  subnetwork_name = local.is_production ? local.prod_subnetwork_name : local.dev_subnetwork_name
  network_name = local.is_production ? local.prod_network_name : local.dev_network_name

  bastion_server_count = var.need_bastion_server ? 1 : 0
}


# CircleCI needs to connect to bastion server
resource "google_compute_firewall" "public_to_bastion_server" {
  count = local.bastion_server_count
  provider = google-beta

  direction               = "INGRESS"
  disabled                = false
  enable_logging          = true
  name                    = "public-to-bastion-server"
  network                 = local.network_name
  priority                = var.firewall_priority_threshold - 1
  project                 = data.google_project.earthranger.project_id
  target_tags             = ["psql-bastion-server-${terraform.workspace}"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "tls_private_key" "bastion_server" {
  algorithm = "RSA"
}

data "google_compute_image" "ubuntu" {
  provider = google

  family  = "ubuntu-1804-lts"
  project = "gce-uefi-images"
}

resource "google_compute_instance" "bastion_server" {
  # Toggle this variable to ensure bastion server spins down after bootstrapping
  count = local.bastion_server_count

  allow_stopping_for_update = "true"
  machine_type              = "g1-small"
  name                      = "psql-bastion-server-${terraform.workspace}"
  project                   = data.google_project.earthranger.project_id
  zone                      = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_zone
  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
    }
  }

  tags = google_compute_firewall.public_to_bastion_server[count.index].target_tags

  labels = {
    role      = "psql-bastion-server"
    workspace = terraform.workspace
  }

  metadata = {
    ssh-keys = "bastion_server:${tls_private_key.bastion_server.public_key_openssh}"
  }

  network_interface {

    subnetwork = local.subnetwork_name

    access_config { # necessary to allocate public ip
    }
  }

  lifecycle {
    ignore_changes = ["attached_disk"]
  }

  provisioner "file" {
    source      = "${path.root}/bastion_server_scripts/postgres_bootstrapping.sql"
    destination = "/home/bastion_server/postgres_bootstrapping.sql"

    connection {
      host        = google_compute_instance.bastion_server[count.index].network_interface.0.access_config.0.nat_ip
      type        = "ssh"
      private_key = "${tls_private_key.bastion_server.private_key_pem}"
      user        = "bastion_server"
    }
  }

  provisioner "remote-exec" {
      connection {
        host        = google_compute_instance.bastion_server[count.index].network_interface.0.access_config.0.nat_ip
        port        = "22"
        private_key = "${tls_private_key.bastion_server.private_key_pem}"
        type        = "ssh"
        user        = "bastion_server"
      }

    script = "${path.root}/bastion_server_scripts/docker_install.sh"

  }

}
