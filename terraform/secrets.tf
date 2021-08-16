resource "kubernetes_secret" "alerts_slack_url" {
  metadata {
    name      = "alerts-slack-url"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = jsondecode(data.google_secret_manager_secret_version.alerts_slack_url.secret_data)
}

resource "kubernetes_secret" "email_username" {
  metadata {
    name      = "email-username"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = jsondecode(data.google_secret_manager_secret_version.email_username.secret_data)
}

resource "kubernetes_secret" "email_password" {
  metadata {
    name      = "email-password"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = jsondecode(data.google_secret_manager_secret_version.email_password.secret_data)
}

resource "kubernetes_secret" "db_password" {
  metadata {
    name      = "db-password"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = jsondecode(data.google_secret_manager_secret_version.db_password.secret_data)
}

resource "kubernetes_secret" "app_db_credentials" {
  metadata {
    name      = "app-db-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    username = google_sql_user.app_user.name
    password = google_sql_user.app_user.password
  }
}

resource "kubernetes_secret" "ssl_certificate_chain" {
  metadata {
    name      = "pamdas-org-ssl-cert-bundle"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = jsondecode(data.google_secret_manager_secret_version.ssl_certificate_chain.secret_data)
}

resource "kubernetes_secret" "ssl_privatekey_pem" {
  metadata {
    name      = "pamdas-org-private-key-pem"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = jsondecode(data.google_secret_manager_secret_version.ssl_privatekey_pem.secret_data)
}

resource "kubernetes_secret" "twilio_account_settings" {
  metadata {
    name      = "twilio-account-settings"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    account_sid          = jsondecode(data.google_secret_manager_secret_version.twilio_account_settings.secret_data).account_sid
    auth_token           = jsondecode(data.google_secret_manager_secret_version.twilio_account_settings.secret_data).auth_token
    whatsapp_from_number = jsondecode(data.google_secret_manager_secret_version.twilio_account_settings.secret_data).whatsapp_from_number
  }
}

resource "kubernetes_secret" "ubi_api_credentials" {
  metadata {
    name      = "ubi-api-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    ubi_username = jsondecode(data.google_secret_manager_secret_version.ubi_api_credentials.secret_data).username
    ubi_password = jsondecode(data.google_secret_manager_secret_version.ubi_api_credentials.secret_data).password
  }
}

resource "kubernetes_secret" "kerlink_credentials" {
  metadata {
    name      = "kerlink-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    kerlink_username = jsondecode(data.google_secret_manager_secret_version.kerlink_credentials.secret_data).username
    kerlink_password = jsondecode(data.google_secret_manager_secret_version.kerlink_credentials.secret_data).password
  }
}

resource "kubernetes_secret" "tableau_api_credentials" {
  metadata {
    name      = "tableau-api-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    tableau_username = jsondecode(data.google_secret_manager_secret_version.tableau_api_credentials.secret_data).username
    tableau_password = jsondecode(data.google_secret_manager_secret_version.tableau_api_credentials.secret_data).password
    tableau_token = jsondecode(data.google_secret_manager_secret_version.tableau_api_credentials.secret_data).token
  }
}
