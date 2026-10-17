# Prywatny bucket ze stroną, dostęp wyłącznie przez CloudFront (OAC).
resource "aws_s3_bucket" "website" {
  bucket        = "${local.name}-web-${local.suffix}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "website" {
  bucket                  = aws_s3_bucket.website.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "website" {
  bucket = aws_s3_bucket.website.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.website.arn}/*"
      Condition = {
        StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.portal.arn }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.website]
}

locals {
  website_origin = "https://${var.domain_name}"
  web_dir        = "${path.module}/../src/web"

  web_files = {
    "index.html"    = "text/html; charset=utf-8"
    "app.js"        = "application/javascript; charset=utf-8"
    "common.js"     = "application/javascript; charset=utf-8"
    "styles.css"    = "text/css; charset=utf-8"
    "mock-pay.html" = "text/html; charset=utf-8"
    "mock-pay.js"   = "application/javascript; charset=utf-8"
  }
}

resource "aws_s3_object" "web" {
  for_each = local.web_files

  bucket        = aws_s3_bucket.website.id
  key           = each.key
  source        = "${local.web_dir}/${each.key}"
  etag          = filemd5("${local.web_dir}/${each.key}")
  content_type  = each.value
  cache_control = "no-cache"
}

resource "aws_s3_object" "config" {
  bucket        = aws_s3_bucket.website.id
  key           = "config.js"
  content_type  = "application/javascript; charset=utf-8"
  cache_control = "no-cache"
  content = "window.APP_CONFIG = ${jsonencode({
    apiUrl     = "/${aws_api_gateway_stage.api.stage_name}"
    maxPhotoMb = var.max_photo_mb
    eventCost  = var.event_cost_credits
    currency   = var.currency
    packages   = var.credit_packages
    categories = var.event_categories
    districts  = local.warsaw_districts
  })};\n"
}
