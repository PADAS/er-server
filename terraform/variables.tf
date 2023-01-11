variable "ertools_cloud_build_identity" {
  type        = string
  default     = "237553880020@cloudbuild.gserviceaccount.com"
  description = "The identity of earthranger-tools cloud build service"
}
/*
  - The pub/sub topics below subscribe to changes on *_sql_analytics_info secret
  - The subscription is on a per kubernetes cluster basis
  - The change notification helps us build a pgbouncer.ini config file
 */
variable "pgb_credentials_topic_dev" {
  type        = string
  default     = "projects/er-reporting-dev/topics/pgb-credentials-dev"
  description = "Holds a reference to a pub/sub topic in er-reporting-dev"
}
variable "pgb_credentials_topic_prod_1" {
  type        = string
  default     = "projects/er-reporting-prod/topics/pgb-credentials-prod1"
  description = "Holds a reference to a pub/sub topic in er-reporting-prod"
}
variable "pgb_credentials_topic_prod_asia" {
  type        = string
  default     = "projects/er-reporting-prod/topics/pgb-credentials-prod-asia"
  description = "Holds a reference to a pub/sub topic in er-reporting-prod"
}
/* Cloud function identities withing er-reporting-dev/prod to be granted read access to the specific *_sql_analytics_info secret */
variable "er_reporting_cfsa_credentials_dev" {
  type        = string
  default     = "cfsa-credentials@er-reporting-dev.iam.gserviceaccount.com"
  description = "Identity of the cloud function that reads a secret and builds a pgbouncer.ini config"
}
variable "er_reporting_cfsa_credentials_prod" {
  type        = string
  default     = "cfsa-credentials@er-reporting-prod.iam.gserviceaccount.com"
  description = "Identity of the cloud function that reads a secret and builds a pgbouncer.ini config"
}
