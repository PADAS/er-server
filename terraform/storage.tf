locals {
  storage_location = data.terraform_remote_state.earthranger_app_infra.outputs.gcp_storage_location
}

resource "google_storage_bucket" "user_uploads" {
  name     = "user-uploads-${kubernetes_namespace.this.metadata.0.name}"
  location = local.storage_location
  project  = data.google_project.earthranger.project_id
  versioning {
    enabled = var.versioning_enabled
  }
}

resource "google_service_account" "earthranger_app_sa" {
  provider   = google
  account_id = substr("er-gcs-${kubernetes_namespace.this.metadata.0.name}", 0, 30)
  project    = data.google_project.earthranger.project_id
}

resource "google_storage_bucket_iam_member" "earthranger_app_writer" {
  bucket = google_storage_bucket.user_uploads.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.earthranger_app_sa.email}"
}

resource "google_project_iam_member" "error_reporting_binding" {
  project = data.google_project.earthranger.id
  role    = "roles/errorreporting.writer"
  member  = "serviceAccount:${google_service_account.earthranger_app_sa.email}"
}

resource "google_project_iam_member" "token_creator_binding" {
  project = data.google_project.earthranger.id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.earthranger_app_sa.email}"
}

resource "google_project_iam_member" "trace_agent_binding" {
  project = data.google_project.earthranger.id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.earthranger_app_sa.email}"
}

resource "google_service_account_key" "er_app_account_key" {
  service_account_id = google_service_account.earthranger_app_sa.name
}

resource "kubernetes_secret" "google-application-credentials" {
  metadata {
    name      = "google-application-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = {
    credentials_json = base64decode(google_service_account_key.er_app_account_key.private_key)
  }
}
