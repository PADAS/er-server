module "vulcan_firewall_access_to_bastion_server" {
  source = "git@github.com:vulcantechnologies/ss-terraform-modules.git//gcp-vulcan-corpnet-firewall?ref=v2.21.0"

  firewall_name = "vulcan-to-bastion-server"
  network_name  = google_compute_network.dev.name
  priority      = var.firewall_priority_threshold - 1
  project_id    = data.google_project.this.project_id
  protocol      = "tcp"
  target_tags   = [bastion_server.name]
}
