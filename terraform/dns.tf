locals {

  alt_subdomains = {
    "connected-conservation"    = "cc"
    "degrees51"                 = "51degrees"
    "niassawcs"                 = "niassa-wcs"
    "kafueccigri"               = "kafuegricci"
    "aberdares"                 = "mountain"
    "meru"                      = "eastern"
    "wisentproject"             = "pwn"
    "pantheraolympic"           = "pantheraolympicpeninsula"
    "wildhorizons"              = "victoriafalls"
    "westernsiempang"           = "spws"
    "abokouamekro"              = "elephants-ci"
    "tsavo-east"                = "tsavo"
    "sca"                       = "southern"
    "tca"                       = "tca-archive"
    "lionlandscapes"            = "lionlandscapestz"
  }

  subdomain_name = lookup(local.alt_subdomains, terraform.workspace, kubernetes_namespace.this.metadata.0.name)

}
resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.public.zone_id
  name    = "${local.subdomain_name}.pamdas.org"
  type    = "A"
  ttl     = 300
  records = [
    google_compute_address.site_ip_address.address
  ]

  depends_on = [
    google_compute_address.site_ip_address,
    kubernetes_namespace.this
  ]
}
