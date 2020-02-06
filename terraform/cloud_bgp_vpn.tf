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

