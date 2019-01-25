resource "azurerm_storage_account" "dev" {
  name                     = "dasdevstorage"   
  resource_group_name      = "${azurerm_resource_group.dev.name}"
  location                 = "${azurerm_resource_group.dev.location}"
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "dev" {
  name                  = "dev-us"
  resource_group_name   = "${azurerm_resource_group.dev.name}"
  storage_account_name  = "${azurerm_storage_account.dev.name}"
}

resource "azurerm_storage_container" "qa" {
  name                  = "qa-us"
  resource_group_name   = "${azurerm_resource_group.dev.name}"
  storage_account_name  = "${azurerm_storage_account.dev.name}"
}

resource "azurerm_storage_container" "stage" {
  name                  = "stage-us"
  resource_group_name   = "${azurerm_resource_group.dev.name}"
  storage_account_name  = "${azurerm_storage_account.dev.name}"
}
