data "aws_route53_zone" "primary" {
  name = "pamdas.org."
}

resource "aws_route53_record" "qa-az" {
  zone_id = "${data.aws_route53_zone.primary.zone_id}"
  name    = "qa-az.${data.aws_route53_zone.primary.name}"
  type    = "A"
  ttl     = "300"
  records = ["13.82.107.180"]
}