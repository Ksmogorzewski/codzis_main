# Docelowa tabela: eventy ze wszystkich źródeł we wspólnym schemacie v1 (src/importer/schema.py),
# otagowane. Pisze do niej wyłącznie tagger ECS.
resource "aws_dynamodb_table" "events" {
  name         = "${local.name}-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  # Zakończone eventy znikają same (darmowe): tagger ustawia expiresAt = koniec + 1 dzień.
  # Zajęcia cykliczne nie mają expiresAt, więc zostają.
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

# Zgłoszenia partnerów ("Moje ogłoszenia"): status queued -> published (ustawia worker).
resource "aws_dynamodb_table" "submissions" {
  name         = "${local.name}-submissions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "partnerId"
    type = "S"
  }

  attribute {
    name = "createdAt"
    type = "S"
  }

  global_secondary_index {
    name            = "byPartner"
    projection_type = "ALL"

    key_schema {
      attribute_name = "partnerId"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
  }
}

# Saldo kredytów partnera (partnerId = id klucza API)
resource "aws_dynamodb_table" "partners" {
  name         = "${local.name}-partners"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "partnerId"

  attribute {
    name = "partnerId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "payments" {
  name         = "${local.name}-payments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "partnerId"
    type = "S"
  }

  attribute {
    name = "createdAt"
    type = "S"
  }

  global_secondary_index {
    name            = "byPartner"
    projection_type = "ALL"

    key_schema {
      attribute_name = "partnerId"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
  }
}

# Prywatny bucket na zdjęcia partnerów: upload przez presigned POST,
# odczyt publicznie przez CloudFront pod https://<domena>/photos/*.
resource "aws_s3_bucket" "photos" {
  bucket        = "${local.name}-photos-${local.suffix}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket                  = aws_s3_bucket.photos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = local.website_origins
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_policy" "photos" {
  bucket = aws_s3_bucket.photos.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.photos.arn}/photos/*"
      Condition = {
        StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.portal.arn }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.photos]
}
