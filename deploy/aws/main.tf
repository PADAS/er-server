/*
Create a <site>.tfvars file for the site/workspace in the sites directory
terraform init

terraform workspace select <partner>-<site>
    or
terraform workspace new <partner>-<site>

terraform plan -var-file="sites/<site>.tfvars"

terraform apply -var-file="sites/<site>.tfvars"
*/

provider "aws" {
  region  = var.aws_region
  version = "~> 2.19"
}

provider "postgresql" {
  host            = "${data.aws_db_instance.db.address}"
  port            = 5432
  username        = var.db_admin_username
  password        = var.db_admin_password
  sslmode         = "require"
  superuser       = false
  connect_timeout = 15
}

resource "aws_s3_bucket" "media-uploads" {
  bucket = "${var.site}-das-media-uploads"
  acl    = "private"
  versioning {
    enabled = true
  }
}

resource "aws_alb" "alb" {
  name            = "${var.site}-das-alb"
  security_groups = [data.aws_security_group.alb_sg.id]
  subnets         = data.aws_subnet_ids.vpc_subnets.ids
}

resource "aws_alb_target_group" "alb-http" {
  name     = "${var.site}-http"
  port     = "80"
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.vpc.id

  health_check {
    healthy_threshold   = "5"
    unhealthy_threshold = "2"
    interval            = "30"
    matcher             = "301"
    path                = "/api/v1.0/status"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = "5"
  }
}

resource "aws_alb_target_group" "alb-https" {
  name     = "${var.site}-http8080"
  port     = "8080"
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.vpc.id

  health_check {
    healthy_threshold   = "5"
    unhealthy_threshold = "2"
    interval            = "30"
    matcher             = "200"
    path                = "/api/v1.0/status"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = "5"
  }
}

resource "aws_alb_listener" "alb-http" {
  load_balancer_arn = aws_alb.alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    target_group_arn = aws_alb_target_group.alb-http.arn
    type             = "forward"
  }
}

resource "aws_alb_listener" "alb-https" {
  load_balancer_arn = aws_alb.alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = data.aws_acm_certificate.ssl_cert.arn

  default_action {
    target_group_arn = aws_alb_target_group.alb-https.arn
    type             = "forward"
  }
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.public.zone_id # Replace with your zone ID
  name    = "${var.site}.pamdas.org"             # Replace with your name/domain/subdomain
  type    = "A"

  alias {
    name                   = aws_alb.alb.dns_name
    zone_id                = aws_alb.alb.zone_id
    evaluate_target_health = false
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = substr("${var.site}-das-redis", 0, 20)
  replication_group_description = "das redis server"
  automatic_failover_enabled    = true
  node_type                     = "cache.t2.micro"
  parameter_group_name          = "das-redis5-0"
  port                          = 6379
  number_cache_clusters         = 2
  engine                        = "redis"
  engine_version                = "5.0.4"
  security_group_ids            = [data.aws_security_group.redis_sg.id]
  apply_immediately             = true
  subnet_group_name             = "das-${var.partner}-vpc-cache-subnet-group"
}

resource "random_string" "db_password" {
  length  = 16
  special = true
}

resource "postgresql_role" "db_role" {
  name     = "${var.site}_user"
  login    = true
  password = random_string.db_password.result
}

resource "postgresql_database" "db" {
  owner    = postgresql_role.db_role.name
  name     = "${var.site}_dasdb"
  encoding = "UTF8"
}

resource "postgresql_extension" "btree_extension" {
  name = "btree_gist"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "unaccent_extension" {
  name = "unaccent"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "uuid_extension" {
  name = "uuid-ossp"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "postgis_extension" {
  name = "postgis"
  database = "${postgresql_database.db.name}"
}

resource "postgresql_extension" "postgis_top_extension" {
  name = "postgis_topology"
  database = "${postgresql_database.db.name}"
  depends_on = [
    postgresql_extension.postgis_extension,
  ]
}

resource "aws_s3_bucket_object" "object" {
  bucket = "${data.aws_s3_bucket.builds.bucket}"
  key = "chef/environments/${var.site}.json"
  content = "${data.template_file.site_json.rendered}"
}
