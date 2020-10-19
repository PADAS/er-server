resource "kubernetes_secret" "alerts_slack_url" {
  metadata {
    name      = "alerts-slack-url"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = data.vault_generic_secret.alerts_slack_url.data
}

resource "kubernetes_secret" "email_username" {
  metadata {
    name      = "email-username"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = data.vault_generic_secret.email_username.data
}

resource "kubernetes_secret" "email_password" {
  metadata {
    name      = "email-password"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = data.vault_generic_secret.email_password.data
}

resource "kubernetes_secret" "db_password" {
  metadata {
    name      = "db-password"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = data.vault_generic_secret.db_password.data
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
  data = data.vault_generic_secret.ssl_certificate_chain.data
}

resource "kubernetes_secret" "ssl_privatekey_pem" {
  metadata {
    name      = "pamdas-org-private-key-pem"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = data.vault_generic_secret.ssl_privatekey_pem.data
}

resource "kubernetes_secret" "twilio_account_settings" {
  metadata {
    name      = "twilio-account-settings"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    account_sid          = data.vault_generic_secret.twilio_account_settings.data.account_sid
    auth_token           = data.vault_generic_secret.twilio_account_settings.data.auth_token
    whatsapp_from_number = data.vault_generic_secret.twilio_account_settings.data.whatsapp_from_number
  }
}

resource "kubernetes_secret" "ubi_api_credentials" {
  metadata {
    name      = "ubi-api-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    ubi_username = data.vault_generic_secret.ubi_api_credentials.data.username
    ubi_password = data.vault_generic_secret.ubi_api_credentials.data.password
  }
}

resource "kubernetes_secret" "kerlink_credentials" {
  metadata {
    name      = "kerlink-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    kerlink_username = data.vault_generic_secret.kerlink_credentials.data.username
    kerlink_password = data.vault_generic_secret.kerlink_credentials.data.password
  }
}

resource "kubernetes_secret" "tableau_api_credentials" {
  metadata {
    name      = "tableau-api-credentials"
    namespace = kubernetes_namespace.this.metadata.0.name
  }

  data = {
    tableau_username = data.vault_generic_secret.tableau_api_credentials.data.username
    tableau_password = data.vault_generic_secret.tableau_api_credentials.data.password
  }
}