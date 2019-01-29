resource "azurerm_storage_account" "bangweulu" {
  name                     = "bangweulustorage"   
  resource_group_name      = "${azurerm_resource_group.er-west-eur.name}"
  location                 = "${azurerm_resource_group.er-west-eur.location}"
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "bangweulu-assets" {
  name                  = "bangweulu-assets"
  resource_group_name   = "${azurerm_resource_group.er-west-eur.name}"
  storage_account_name  = "${azurerm_storage_account.bangweulu.name}"
}

