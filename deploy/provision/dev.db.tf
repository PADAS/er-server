resource "azurerm_resource_group" "dev" {
  name     = "DAS-Dev"
  location = "West US"
}

resource "azurerm_postgresql_server" "dev" {
  name                = "das-postgres-us-tf"
  location            = "${azurerm_resource_group.dev.location}"
  resource_group_name = "${azurerm_resource_group.dev.name}"

  sku {
    name     = "GP_Gen5_2"
    capacity = 2
    tier     = "GeneralPurpose"
    family   = "Gen5"
  }

  storage_profile {
    storage_mb            = 5120
    backup_retention_days = 7
    geo_redundant_backup  = "Disabled"
  }

  administrator_login          = "postgres"
  administrator_login_password = "H@Sh1CoR3!"
  version                      = "9.6"
  ssl_enforcement              = "Enabled"
}

resource "azurerm_postgresql_database" "dev" {
  name                = "dev"
  resource_group_name = "${azurerm_resource_group.dev.name}"
  server_name         = "${azurerm_postgresql_server.dev.name}"
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_postgresql_database" "qa" {
  name                = "qa"
  resource_group_name = "${azurerm_resource_group.dev.name}"
  server_name         = "${azurerm_postgresql_server.dev.name}"
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_postgresql_database" "stge" {
  name                = "stage"
  resource_group_name = "${azurerm_resource_group.dev.name}"
  server_name         = "${azurerm_postgresql_server.dev.name}"
  charset             = "UTF8"
  collation           = "English_United States.1252"
}

resource "azurerm_postgresql_firewall_rule" "all_azure" {
  name                = "All_Azure"
  resource_group_name = "${azurerm_resource_group.dev.name}"
  server_name         = "${azurerm_postgresql_server.dev.name}"
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"
}

resource "azurerm_postgresql_firewall_rule" "corp_egress" {
  name                = "Vulcan_Egress"
  resource_group_name = "${azurerm_resource_group.dev.name}"
  server_name         = "${azurerm_postgresql_server.dev.name}"
  start_ip_address    = "216.220.194.1"
  end_ip_address      = "216.220.194.254"
}
