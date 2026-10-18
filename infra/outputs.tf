output "portal_url" {
  value = local.website_origin
}

# terraform output -json partner_api_keys
output "partner_api_keys" {
  value     = { for name, key in aws_api_gateway_api_key.partner : name => key.value }
  sensitive = true
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.portal.domain_name
}

output "tables" {
  value = {
    events      = aws_dynamodb_table.events.name
    submissions = aws_dynamodb_table.submissions.name
    partners    = aws_dynamodb_table.partners.name
    payments    = aws_dynamodb_table.payments.name
  }
}

output "photos_bucket" {
  value = aws_s3_bucket.photos.id
}

output "region" {
  value = var.region
}

output "events_queue_url" {
  value = aws_sqs_queue.events.url
}

output "worker_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "deepseek_api_key_parameter" {
  description = "Ustaw wartość: aws ssm put-parameter --name <to> --type SecureString --overwrite --value sk-..."
  value       = aws_ssm_parameter.deepseek_api_key.name
}

output "google_maps_embed_key_parameter" {
  description = "Ustaw wartość: aws ssm put-parameter --name <to> --type SecureString --overwrite --value AIza..., potem terraform apply"
  value       = aws_ssm_parameter.google_maps_embed_key.name
}

output "importer_repository_url" {
  value = aws_ecr_repository.importer.repository_url
}

output "um_api_token_parameter" {
  description = "Ustaw wartość: aws ssm put-parameter --name <to> --type SecureString --overwrite --value <token>"
  value       = aws_ssm_parameter.um_api_token.name
}

output "data_bucket" {
  value = aws_s3_bucket.data.id
}

# --- dla scripts/run-task.sh i scripts/initial-load.sh ---

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "task_subnets" {
  value = join(",", aws_subnet.public[*].id)
}

output "task_security_group" {
  value = aws_security_group.worker.id
}

output "importer_task_family" {
  value = aws_ecs_task_definition.importer.family
}

output "tagger_task_family" {
  value = aws_ecs_task_definition.worker.family
}

output "events_dlq_url" {
  value = aws_sqs_queue.events_dlq.url
}

# --- rekordy DNS do dodania ręcznie w home.pl ---

output "acm_validation_records" {
  description = "CNAME do walidacji certyfikatu (dodaj w home.pl i zostaw na stałe)"
  value = [for o in aws_acm_certificate.portal.domain_validation_options : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}

output "dns_records" {
  description = "Domeny portalu -> CloudFront. Domena główna wymaga typu ALIAS/ANAME (CNAME na apexie jest niedozwolony)"
  value = [for d in local.portal_domains : {
    name  = d
    type  = length(split(".", d)) > 2 ? "CNAME" : "ALIAS / ANAME"
    value = aws_cloudfront_distribution.portal.domain_name
  }]
}

# --- portal klienta ---

output "client_url" {
  value = "https://${var.client_domain_name}"
}

output "client_acm_validation_records" {
  description = "CNAME do walidacji certyfikatu portalu klienta (dodaj w home.pl i zostaw na stałe)"
  value = [for o in aws_acm_certificate.client.domain_validation_options : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}

output "client_dns_records" {
  description = "Domeny portalu klienta -> CloudFront (home.pl: CNAME, Host = część przed .waw-out.pl)"
  value = [for d in local.client_domains : {
    name  = d
    type  = length(split(".", d)) > 2 ? "CNAME" : "ALIAS (niedostępny w home.pl)"
    value = aws_cloudfront_distribution.client.domain_name
  }]
}

output "client_api_url" {
  value = aws_apigatewayv2_api.client.api_endpoint
}

output "cognito_hosted_ui" {
  description = "Hosted UI Cognito portalu klienta i panelu organizatora (Authorized JavaScript origins klienta OAuth Google); domeny powstają po włączeniu Google"
  value       = ["https://${local.cognito_hosted_domain}", "https://${local.partner_cognito_domain}"]
}

output "google_oauth_redirect_uris" {
  description = "Przed włączeniem Google: wpisz oba w Google Cloud Console jako Authorized redirect URIs klienta OAuth"
  value = [
    "https://${local.cognito_hosted_domain}/oauth2/idpresponse",
    "https://${local.partner_cognito_domain}/oauth2/idpresponse",
  ]
}

output "partner_app_config" {
  description = "Konfiguracja panelu organizatora (to samo trafia do config.js na S3)"
  value       = local.partner_app_config
}

output "client_app_config" {
  description = "Konfiguracja strony klienta (to samo trafia do config.js na S3)"
  value       = local.client_app_config
}

# --- rekomendacje (RAG): scripts/push-images.sh recommender, scripts/recommender-refresh.sh ---

output "recommender_repository_url" {
  value = aws_ecr_repository.recommender.repository_url
}

output "recommender_function" {
  value = aws_lambda_function.recommender.function_name
}

output "google_oauth_secret" {
  description = "Sekret AWS Secrets Manager z klientem OAuth Google: put-secret-value z JSON-em client_id, client_secret"
  value       = local.google_secret_name
}

output "google_login_enabled" {
  description = "Czy logowanie Google jest włączone (sekret istnieje i ma prawdziwy client_id)"
  value       = local.google_enabled
}
