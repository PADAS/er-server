resource "google_service_account" "earthranger_app_sa" {
  provider   = google
  account_id = "er-gcs-${kubernetes_namespace.this.metadata.0.name}"
  project    = data.google_project.earthranger.project_id
}

resource "google_project_iam_member" "earthranger_gcs_writer" {
  provider = google
  member   = "serviceAccount:${google_service_account.earthranger_app_sa.email}"
  project  = data.google_project.earthranger.project_id
  role     = "roles/storage.objectWriter"
}

resource "google_service_account_key" "er_app_account_key" {
  service_account_id = google_service_account.earthranger_app_sa.name
}

resource "kubernetes_secret" "google-application-credentials" {
  metadata {
    name = "google-application-credentials"
  }
  data = {
    credentials_json = base64decode(google_service_account_key.er_app_account_key.private_key)
  }
}
