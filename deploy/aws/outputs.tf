output "tg_http_arn" {
  value = aws_alb_target_group.alb-http.arn
}

output "tg_https_arn" {
  value = aws_alb_target_group.alb-https.arn
}

