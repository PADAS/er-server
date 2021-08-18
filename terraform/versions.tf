terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>2.44"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 3.79"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">=2.19"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 1.10"
    }
    random = {
      source  = "hashicorp/random"
      version = ">=2.1"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">=2.1"
    }
  }
  required_version = ">= 0.13"
}
