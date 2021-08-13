data "google_project" "earthranger" {
  project_id = "earthranger-78ca55ca"
}

data "google_secret_manager_secret_version" "aws_metrics_credentials" {
  project = data.google_project.earthranger.project_id
  secret  = "aws_metrics_credentials"
}

data "google_secret_manager_secret_version" "ga_measurement_id" {
  project = data.google_project.earthranger.project_id
  secret  = "ga_measurement_id"
}
