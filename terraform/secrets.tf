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

