# Dev VPC network 
resource "google_compute_network" "dev_vpc_network" {
  name                    = "dev"
  auto_create_subnetworks = false
}

# Create dev subnet
#----------------------------------------
resource "google_compute_subnetwork" "dev_subnet" {
  name                     = "dev"
  ip_cidr_range            = "10.100.0.0/20"
  private_ip_google_access = true
  network                  = google_compute_network.dev_vpc_network.name
  region                   = "us-west1" #dynamically add
}

# Cloud Router enables you to dynamically exchange routes between your Virtual Private Cloud (VPC) 
# and on-premises networks by the using of Borderway Gateway Protocol
resource "google_compute_router" "dev" {
  name    = "aws-gcp-router"
  network = google_compute_network.dev_vpc_network.name
  project = data.google_project.earthranger.project_id
  region  = "us-west1" #dynamically add
  bgp {
    asn               = 65001
    advertise_mode    = "CUSTOM"
    advertised_groups = ["ALL_SUBNETS"]
    advertised_ip_ranges {
      range = "10.100.0.0/20"
    }
    advertised_ip_ranges {
      range = "10.48.0.0/14"
    }
    advertised_ip_ranges {
      range = "10.241.0.0/20"
    }

  }

}

# Get static address to be used in forwarding rules
resource "google_compute_address" "vpn_static_ip" {
  name    = "vpn-1"
  address = "34.83.25.105" #set this dynamically
}

# Forwarding rules
resource "google_compute_forwarding_rule" "vpn_1_rule_esp" {
  name        = "vpn-1-rule-esp"
  ip_protocol = "ESP"
  ip_address  = google_compute_address.vpn_static_ip.address
  target      = google_compute_vpn_gateway.dev_gateway.self_link
}

resource "google_compute_forwarding_rule" "vpn_1_rule_udp500" {
  name        = "vpn-1-rule-udp500"
  ip_protocol = "UDP"
  port_range  = "500"
  ip_address  = google_compute_address.vpn_static_ip.address
  target      = google_compute_vpn_gateway.dev_gateway.self_link
}

resource "google_compute_forwarding_rule" "vpn_1_rule_udp4500" {
  name        = "vpn-1-rule-udp4500"
  ip_protocol = "UDP"
  port_range  = "4500"
  ip_address  = google_compute_address.vpn_static_ip.address
  target      = google_compute_vpn_gateway.dev_gateway.self_link
}
# VPN gateway

resource "google_compute_vpn_gateway" "dev_gateway" {
  provider = google
  name     = "vpn-1"
  network  = google_compute_network.dev_vpc_network.name
}

# Each tunnel is responsible for encrypting and decrypting traffic exiting
# and leaving its associated gateway
# We will create 2 tunnels to aws on same GCP VPN gateway

# Create Tunnel1
#--------------------------------------------
resource "google_compute_vpn_tunnel" "dev_tunnel1" {
  name          = "vpn-1-tunnel-1"
  ike_version   = 1
  peer_ip       = "52.36.71.252"
  shared_secret = "" #store in vault
  project       = data.google_project.earthranger.project_id
  region        = "us-west1" #dynamically add

  timeouts {
    create = "4m"
    delete = "4m"
  }

  router             = google_compute_router.dev.self_link
  target_vpn_gateway = google_compute_vpn_gateway.dev_gateway.self_link

  depends_on = [
    google_compute_forwarding_rule.vpn_1_rule_esp,
    google_compute_forwarding_rule.vpn_1_rule_udp500,
    google_compute_forwarding_rule.vpn_1_rule_udp4500,
  ]

}

# VPN Tunnel2
resource "google_compute_vpn_tunnel" "dev_tunnel2" {
  name          = "vpn-1-tunnel-2"
  ike_version   = 1
  peer_ip       = "54.68.48.172"
  shared_secret = "" #store in vault
  project       = data.google_project.earthranger.project_id
  region        = "us-west1" #dynamically add

  timeouts {
    create = "4m"
    delete = "4m"
  }

  router             = google_compute_router.dev.self_link
  target_vpn_gateway = google_compute_vpn_gateway.dev_gateway.self_link

  depends_on = [
    google_compute_forwarding_rule.vpn_1_rule_esp,
    google_compute_forwarding_rule.vpn_1_rule_udp500,
    google_compute_forwarding_rule.vpn_1_rule_udp4500,
  ]

}

