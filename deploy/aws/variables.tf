variable "aws_region" {
  description = "AWS region to launch servers."
  default     = "eu-central-1"
}

variable "build_version" {
    description = "DAS build number, 1.70.1-rc.15"
    default = "1.70.1-rc.15"
}
variable "site" {
  description = "Name of site, used for naming resources and dns"
}

variable "partner" {
  description = "Partner name"
  default     = "prod"
}

variable "rds_name" {
  description = "PostgreSQL server name in RDS"
  default     = "prod-01-das-db"
}

variable "db_admin_password" {
  description = "PostgreSQL server password"
}

variable "db_admin_username" {
  description = "PostgreSQL admin username, default postgres"
  default     = "postgres"
}

variable "timezone" {
  description = "Timezone used by the site, look in pytz for examples"
  default     = "Africa/Nairobi"
}

variable "zendesk_name" {
  default = ""
}

variable "zendesk_email" {
  default = ""
}

variable "zendesk_organization" {
  default = ""
}

variable "track_days" {
  default = 16
}

variable "show_stationary_subjects_on_map" {
  default = "False"
}

data "aws_s3_bucket" "builds" {
  bucket = "${var.partner}-das-builds"
}

data "aws_iam_role" "ec2_role" {
  name = "das_prod_role"
}

data "aws_acm_certificate" "ssl_cert" {
  domain   = "*.pamdas.org"
  statuses = ["ISSUED"]
}

data "aws_db_instance" "db" {
  db_instance_identifier = var.rds_name
}

data "aws_vpc" "vpc" {
  id = "vpc-020cacb36b0ce0a78"
}

data "aws_subnet_ids" "vpc_subnets" {
  vpc_id = data.aws_vpc.vpc.id
}

data "aws_security_group" "redis_sg" {
  name = "das_prod_redis"
}

data "aws_security_group" "admin_sg" {
  name = "das_prod_admin"
}

data "aws_security_group" "db_sg" {
  name = "das_prod_postres_db"
}

data "aws_security_group" "alb_sg" {
  name = "das_prod_public_elb"
}

data "aws_security_group" "ec2_sg" {
  name = "das_prod_pipeline_instance"
}

data "aws_route53_zone" "public" {
  name = "pamdas.org."
}

data "template_file" "site_json" {
  template = file("./er_chef_settings.tpl.json")
  vars = {
    build_version                   = var.build_version
    site                            = var.site
    s3_bucket                       = data.aws_s3_bucket.builds.bucket
    db_host                         = data.aws_db_instance.db.address
    db_name                         = postgresql_database.db.name
    db_user                         = postgresql_role.db_role.name
    db_password                     = random_string.db_password.result
    media_uploads                   = aws_s3_bucket.media-uploads.bucket
    media_uploads_region            = aws_s3_bucket.media-uploads.region
    redis_host                      = aws_elasticache_replication_group.redis.primary_endpoint_address
    timezone                        = var.timezone
    zendesk_email                   = var.zendesk_email
    zendesk_name                    = var.zendesk_name
    zendesk_organization            = var.zendesk_organization
    track_days                      = var.track_days
    kml_feed_title                  = "${var.site} Tracking Service"
    show_stationary_subjects_on_map = var.show_stationary_subjects_on_map
  }
}

