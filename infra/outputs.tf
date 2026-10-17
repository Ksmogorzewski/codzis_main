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
