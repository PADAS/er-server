resource "azurerm_resource_group" "er-west-eur" {
  name     = "er-west-europe"
  location = "West Europe"
}

resource "azurerm_postgresql_server" "er-west-eur" {
  name                = "das-postgres-west-europe"
  location            = "${azurerm_resource_group.er-west-eur.location}"
  resource_group_name = "${azurerm_resource_group.er-west-eur.name}"

  sku {
    name     = "GP_Gen5_4"
    capacity = 4
    tier     = "GeneralPurpose"
    family   = "Gen5"
  }

  storage_profile {
    storage_mb            = 10240
    backup_retention_days = 7
    geo_redundant_backup  = "Disabled"
  }

  administrator_login          = "postgres"
  administrator_login_password = "nt9Oggx7ztOd7fK9lx3vFLRT"
  version                      = "9.6"
  ssl_enforcement              = "Enabled"
}

resource "azurerm_postgresql_database" "bangweulu" {
  name                = "bangweulu"
  resource_group_name = "${azurerm_resource_group.er-west-eur.name}"
  server_name         = "${azurerm_postgresql_server.er-west-eur.name}"
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_postgresql_firewall_rule" "all_azure_w_eur" {
  name                = "All_Azure"
  resource_group_name = "${azurerm_resource_group.er-west-eur.name}"
  server_name         = "${azurerm_postgresql_server.er-west-eur.name}"
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"
}

resource "azurerm_postgresql_firewall_rule" "corp_egress_w_eur" {
  name                = "Vulcan_Egress"
  resource_group_name = "${azurerm_resource_group.er-west-eur.name}"
  server_name         = "${azurerm_postgresql_server.er-west-eur.name}"
  start_ip_address    = "216.220.194.1"
  end_ip_address      = "216.220.194.254"
}
