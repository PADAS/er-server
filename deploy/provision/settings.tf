provider "azurerm" {
  # pin the version of the provider being used
  version = "=1.21.0"

  subscription_id = "c4f7019a-487c-4211-a8ae-377fa0a0a0aa"
}

provider "aws" {
  # pin the version of the provider being used  
  version = "=1.56.0"

  region = "us-west-2"

}