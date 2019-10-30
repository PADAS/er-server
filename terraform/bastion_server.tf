locals {
  is_production = (terraform.workspace == "prod")
  dev_subnetwork_name = data.terraform_remote_state.terraform_gcp.outputs.dev_us_west_1_subnetwork_name
  prod_subnetwork_name = data.terraform_remote_state.terraform_gcp.outputs.prod_europe_west_3_subnetwork_name


  dev_network_name = data.terraform_remote_state.terraform_gcp.outputs.dev_network_name
  prod_network_name = data.terraform_remote_state.terraform_gcp.outputs.prod_network_name

  subnetwork_name = local.is_production ? local.prod_subnetwork_name : local.dev_subnetwork_name
  network_name = local.is_production ? local.prod_network_name : local.dev_network_name
}

module "vulcan_firewall_access_to_bastion_server" {
  source = "git@github.com:vulcantechnologies/ss-terraform-modules.git//gcp-vulcan-corpnet-firewall?ref=v2.21.0"

  firewall_name = "vulcan-to-bastion-server"
  network_name  = local.network_name
  priority      = var.firewall_priority_threshold - 1
  project_id    = data.google_project.this.project_id
  protocol      = "tcp"
  target_tags   = [google_compute_instance.bastion_server.name]
}

resource "tls_private_key" "bastion_server" {
  algorithm = "RSA"
}

data "google_compute_image" "container_optimized_os" {
  provider = google

  family  = "ubuntu-1804-lts"
  project = "gce-uefi-images"
}

resource "google_compute_instance" "bastion_server" {
  allow_stopping_for_update = "true"
  machine_type              = "g1-small"
  name                      = "psql-bastion-server-${terraform.workspace}"
  project                   = data.google_project.this.project_id
  zone                      = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_zone
  boot_disk {
    initialize_params {
      image = data.google_compute_image.container_optimized_os.self_link
    }
  }

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
    source      = "${path.root}/postgres_bootstrapping.sql"
    destination = "/home/bastion_server/postgres_bootstrapping.sql"

    connection {
      host        = google_compute_instance.bastion_server.network_interface.0.access_config.0.nat_ip
      type        = "ssh"
      private_key = "${tls_private_key.bastion_server.private_key_pem}"
      user        = "bastion_server"
    }
  }

  tags = [
    "psql-bastion-server-${terraform.workspace}"
  ]
}
