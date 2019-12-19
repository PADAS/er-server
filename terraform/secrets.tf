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

resource "kubernetes_secret" "pamdas_org_ssl_ca" {
  metadata {
    name      = "pamdas-org-ssl-ca"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = data.vault_generic_secret.pamdas_org_ssl_ca.data
}

resource "kubernetes_secret" "pamdas_org_ssl_cert" {
  metadata {
    name      = "pamdas-org-ssl-cert"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = data.vault_generic_secret.pamdas_org_ssl_cert.data
}

resource "kubernetes_secret" "pamdas_org_ssl_key" {
  metadata {
    name      = "pamdas-org-ssl-key"
    namespace = kubernetes_namespace.this.metadata.0.name
  }
  data = data.vault_generic_secret.pamdas_org_ssl_key.data
}

