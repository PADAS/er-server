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
  shared_secret = data.vault_generic_secret.tunnel1_ikev1_pre_shared_key.data["value"]
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
  shared_secret = data.vault_generic_secret.tunnel2_ikev1_pre_shared_key.data["value"]
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



# BGP one router interface
resource "google_compute_router_interface" "tunnel1" {
  name       = "interface-1"
  router     = google_compute_router.dev.name
  region     = "us-west1" #Add dynamically
  project    = data.google_project.earthranger.project_id
  ip_range   = "169.254.95.132/30"
  vpn_tunnel = google_compute_vpn_tunnel.dev_tunnel1.name
}

# BGP two router interface
resource "google_compute_router_interface" "tunnel2" {
  name       = "interface-2"
  router     = google_compute_router.dev.name
  region     = "us-west1" #Add dynamically
  project    = data.google_project.earthranger.project_id
  ip_range   = "169.254.115.204/30"
  vpn_tunnel = google_compute_vpn_tunnel.dev_tunnel2.name
}

# BGP Peer One
resource "google_compute_router_peer" "bgp-peer-one" {
  name                      = "bgpone" #better naming convention?
  router                    = google_compute_router.dev.name
  project                   = data.google_project.earthranger.project_id
  region                    = "us-west1" #dynamically add
  peer_ip_address           = "169.254.95.133"
  peer_asn                  = 65002
  advertised_route_priority = 100
  interface                 = google_compute_router_interface.tunnel1.name

  depends_on = [
    google_compute_router_interface.tunnel1
  ]
}

# BGP Peer two
resource "google_compute_router_peer" "bgp-peer-two" {
  name                      = "bgptwo" #better naming convention?
  router                    = google_compute_router.dev.name
  project                   = data.google_project.earthranger.project_id
  region                    = "us-west1" #dynamically add
  peer_ip_address           = "169.254.115.205"
  peer_asn                  = 65002
  advertised_route_priority = 100
  interface                 = google_compute_router_interface.tunnel2.name

  depends_on = [
    google_compute_router_interface.tunnel2
  ]
}
