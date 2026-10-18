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
  portal_domains  = concat([var.domain_name], var.domain_aliases)
  website_origin  = "https://${var.domain_name}" # adres kanoniczny (zdjęcia, linki)
  website_origins = [for d in local.portal_domains : "https://${d}"]

  # Build Reacta: npm --prefix src/frontend run build (patrz terraform_data.frontend_build)
  web_dir = "${path.module}/../src/frontend/dist/partner"
  # config.js z lokalnego developmentu (scripts/frontend-dev.sh) mógł trafić do builda - na S3 idzie wersja z Terraforma
  web_files = setsubtract(fileset(local.web_dir, "**"), ["config.js"])

  partner_app_config = {
    apiUrl       = "/${aws_api_gateway_stage.api.stage_name}"
    maxPhotoMb   = var.max_photo_mb
    eventCost    = var.event_cost_credits
    currency     = var.currency
    packages     = var.credit_packages
    categories   = var.event_categories
    districts    = local.warsaw_districts
    clientPortal = "https://${var.client_domain_name}"
    # Logowanie Google (partner_auth.tf); puste = logowanie kluczem API
    cognitoDomain = local.google_enabled ? local.partner_cognito_domain : ""
    clientId      = local.google_enabled ? aws_cognito_user_pool_client.partner_web[0].id : ""
  }
}

# Bez zbudowanego frontendu fileset() byłby pusty i apply skasowałby strony z S3 - zatrzymujemy plan
resource "terraform_data" "frontend_build" {
  lifecycle {
    precondition {
      condition     = fileexists("${local.web_dir}/index.html") && fileexists("${local.client_web_dir}/index.html")
      error_message = "Brak zbudowanego frontendu (src/frontend/dist). Uruchom: npm --prefix src/frontend ci && npm --prefix src/frontend run build"
    }
  }
}

resource "aws_s3_object" "web" {
  for_each = local.web_files

  bucket        = aws_s3_bucket.website.id
  key           = each.key
  source        = "${local.web_dir}/${each.key}"
  etag          = filemd5("${local.web_dir}/${each.key}")
  content_type  = lookup(local.content_types, regex("[^.]+$", each.key), "application/octet-stream")
  cache_control = startswith(each.key, "assets/") ? "public, max-age=86400" : "no-cache"
}

resource "aws_s3_object" "config" {
  bucket        = aws_s3_bucket.website.id
  key           = "config.js"
  content_type  = "application/javascript; charset=utf-8"
  cache_control = "no-cache"
  content       = "window.APP_CONFIG = ${jsonencode(local.partner_app_config)};\n"
}
