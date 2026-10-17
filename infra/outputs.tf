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
