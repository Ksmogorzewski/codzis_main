# DNS domeny jest w home.pl, bez Route53. Rekordy dodajesz tam ręcznie - Terraform je wypisuje:
#   terraform output acm_validation_records   (walidacja certyfikatu; zostają na stałe - auto-odnawianie)
#   terraform output dns_records              (domeny portalu -> CloudFront)
resource "aws_acm_certificate" "portal" {
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = var.domain_aliases
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Czeka (do 2 h), aż certyfikat będzie ISSUED, czyli aż rekordy walidacyjne pojawią się w home.pl
resource "aws_acm_certificate_validation" "portal" {
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.portal.arn

  timeouts {
    create = "2h"
  }
}

resource "aws_cloudfront_origin_access_control" "website" {
  name                              = "${local.name}-s3"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

# Przekazuje m.in. x-api-key; Host musi zostać execute-api, inaczej API GW odrzuci żądanie.
data "aws_cloudfront_origin_request_policy" "all_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "portal" {
  enabled             = true
  is_ipv6_enabled     = true
  aliases             = local.portal_domains
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    origin_id                = "website"
    domain_name              = aws_s3_bucket.website.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.website.id
  }

  origin {
    origin_id                = "photos"
    domain_name              = aws_s3_bucket.photos.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.website.id
  }

  # /api/* -> stage "api" w API GW (ścieżka przechodzi 1:1, bez przepisywania).
  origin {
    origin_id   = "api"
    domain_name = "${aws_api_gateway_rest_api.api.id}.execute-api.${var.region}.amazonaws.com"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "website"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  # /photos/<id>/photo.jpg -> klucz photos/<id>/photo.jpg w buckecie zdjęć
  ordered_cache_behavior {
    path_pattern           = "/photos/*"
    target_origin_id       = "photos"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  ordered_cache_behavior {
    path_pattern             = "/${aws_api_gateway_stage.api.stage_name}/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_except_host.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.portal.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
