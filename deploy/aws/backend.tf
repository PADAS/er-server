terraform {
 backend "s3" {
   bucket         = "prod-das-builds"
   key            = "tf/das.tfstate"
   region         = "eu-central-1"
   encrypt        = true
  }
}