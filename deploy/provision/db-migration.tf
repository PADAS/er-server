resource "azurerm_storage_account" "db_migration" {
  name                     = "dasmigration"   
  resource_group_name      = "${azurerm_resource_group.er-west-eur.name}"
  location                 = "${azurerm_resource_group.er-west-eur.location}"
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "db_dumps" {
  name                  = "db-dumps"
  resource_group_name   = "${azurerm_resource_group.er-west-eur.name}"
  storage_account_name  = "${azurerm_storage_account.db_migration.name}"
}

