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


