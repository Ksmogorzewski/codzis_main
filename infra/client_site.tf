# Strona klienta (WarsawNow) na głównej domenie: S3 (prywatny) + CloudFront.
# CloudFront jest tu po to, żeby mieć HTTPS na własnej domenie (Cognito i Google wymagają https
# dla adresów powrotu po logowaniu), a nie dla zasięgu globalnego. DNS: home.pl (rekordy ręcznie).

resource "aws_s3_bucket" "client_web" {
  bucket        = "${local.name}-client-${local.suffix}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "client_web" {
  bucket                  = aws_s3_bucket.client_web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "client_web" {
  bucket = aws_s3_bucket.client_web.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.client_web.arn}/*"
      Condition = {
        StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.client.arn }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.client_web]
}

resource "aws_acm_certificate" "client" {
  provider                  = aws.us_east_1
  domain_name               = var.client_domain_name
  subject_alternative_names = var.client_domain_aliases
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Czeka (do 2 h), aż rekordy walidacyjne pojawią się w home.pl: terraform output client_acm_validation_records
resource "aws_acm_certificate_validation" "client" {
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.client.arn

  timeouts {
    create = "2h"
  }
}

resource "aws_cloudfront_distribution" "client" {
  enabled             = true
  is_ipv6_enabled     = true
  aliases             = local.client_domains
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # krawędzie w Europie i Ameryce Płn. - użytkownicy są w Warszawie

  origin {
    origin_id                = "client-web"
    domain_name              = aws_s3_bucket.client_web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.website.id
  }

  default_cache_behavior {
    target_origin_id       = "client-web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.client.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

locals {
  # Build Reacta: npm --prefix src/frontend run build (patrz terraform_data.frontend_build)
  client_web_dir = "${path.module}/../src/frontend/dist/client"
  # config.js z lokalnego developmentu (scripts/frontend-dev.sh) mógł trafić do builda - na S3 idzie wersja z Terraforma
  client_web_files = setsubtract(fileset(local.client_web_dir, "**"), ["config.js"])
}

resource "aws_s3_object" "client_web" {
  for_each = local.client_web_files

  bucket        = aws_s3_bucket.client_web.id
  key           = each.key
  source        = "${local.client_web_dir}/${each.key}"
  etag          = filemd5("${local.client_web_dir}/${each.key}")
  content_type  = lookup(local.content_types, regex("[^.]+$", each.key), "application/octet-stream")
  cache_control = startswith(each.key, "assets/") ? "public, max-age=86400" : "no-cache"
}

resource "aws_s3_object" "client_config" {
  bucket        = aws_s3_bucket.client_web.id
  key           = "config.js"
  content_type  = "application/javascript; charset=utf-8"
  cache_control = "no-cache"
  content       = "window.APP_CONFIG = ${jsonencode(local.client_app_config)};\n"
}

locals {
  client_app_config = {
    region        = var.region
    userPoolId    = aws_cognito_user_pool.clients.id
    clientId      = aws_cognito_user_pool_client.web.id
    cognitoDomain = local.cognito_hosted_domain
    googleEnabled = local.google_enabled
    apiUrl        = aws_apigatewayv2_api.client.api_endpoint
    partnerPortal = local.website_origin
  }
}
