# Rekomendacje (RAG): Lambda z obrazu kontenera (src/recommender_api + pakiet recommender/).
# Indeks wektorów eventów leży w buckecie danych (recommender/index.npz). EventBridge odświeża go
# przyrostowo i trzyma model w pamięci. GET /api/recommendations idzie przez HTTP API klienta (JWT Cognito).
# Gotowe zestawy kart trafiają do tabeli recommendations: na dziś, jutro i weekend liczą się w nocy,
# po zmianie profilu i przy logowaniu (client-api wywołuje Lambdę asynchronicznie), resztę przy pierwszym
# zapytaniu - zawsze w tle (GET zleca liczenie samej sobie), więc limit 30 s HTTP API nie ogranicza AI.
#
# Lambda wymaga istniejącego obrazu, więc pierwsze wdrożenie jest dwuetapowe:
#   terraform apply -target=aws_ecr_repository.recommender
#   scripts/push-images.sh recommender
#   terraform apply
#   scripts/recommender-refresh.sh      # pierwszy indeks (embedding wszystkich eventów, ~1-3 min)

resource "aws_ecr_repository" "recommender" {
  name                 = "${local.name}-recommender"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "recommender" {
  repository = aws_ecr_repository.recommender.name
  policy     = aws_ecr_lifecycle_policy.worker.policy
}

# Lambda pobiera obraz z ECR
resource "aws_ecr_repository_policy" "recommender" {
  repository = aws_ecr_repository.recommender.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaPull"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      Condition = {
        StringLike = { "aws:sourceArn" = "arn:aws:lambda:${var.region}:${local.suffix}:function:*" }
      }
    }]
  })
}

# Digest obrazu z danym tagiem: po `scripts/push-images.sh recommender` kolejny apply podmienia kod
data "aws_ecr_image" "recommender" {
  repository_name = aws_ecr_repository.recommender.name
  image_tag       = var.recommender_image_tag
}

# Zapisane zestawy rekomendacji per użytkownik (src/recommender_api/results_store.py)
resource "aws_dynamodb_table" "recommendations" {
  name         = "${local.name}-recommendations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "setKey" # okno#od#do#limit#fraza

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "setKey"
    type = "S"
  }

  # Zestawy znikają same dzień po końcu swojego okna
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }
}

resource "aws_cloudwatch_log_group" "recommender" {
  name              = "/aws/lambda/${local.name}-recommender"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "recommender" {
  name = "${local.name}-recommender"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "recommender" {
  name = "${local.name}-recommender"
  role = aws_iam_role.recommender.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.recommender.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = aws_dynamodb_table.events.arn
      },
      {
        # Scan: nocne przeliczenie zestawów dla aktywnych użytkowników
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Scan"]
        Resource = aws_dynamodb_table.users.arn
      },
      {
        # UpdateItem: claim liczenia (i jego zdjęcie) na rekordzie zestawu, PutItem: gotowy zestaw
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.recommendations.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.data.arn}/recommender/*"
      },
      {
        # Bez ListBucket brak pliku indeksu daje 403 zamiast 404
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.data.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = aws_ssm_parameter.deepseek_api_key.arn
      },
      {
        # GET zleca liczenie zestawu w tle (asynchroniczne wywołanie samej siebie);
        # ARN złożony ręcznie, bo funkcja zależy od tej polityki
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:${var.region}:${local.suffix}:function:${local.name}-recommender"
      },
    ]
  })
}

resource "aws_lambda_function" "recommender" {
  function_name = "${local.name}-recommender"
  role          = aws_iam_role.recommender.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.recommender.repository_url}@${data.aws_ecr_image.recommender.image_digest}"
  architectures = ["arm64"]
  memory_size   = var.recommender_memory_mb
  # Pełna przebudowa indeksu potrafi trwać kilka minut; zapytania z API i tak ucina HTTP API po 30 s
  timeout = 900

  environment {
    variables = {
      EVENTS_TABLE           = aws_dynamodb_table.events.name
      USERS_TABLE            = aws_dynamodb_table.users.name
      RESULTS_TABLE          = aws_dynamodb_table.recommendations.name
      RESULTS_MAX_AGE_HOURS  = tostring(var.recommender_results_max_age_hours)
      PRECOMPUTE_ACTIVE_DAYS = tostring(var.recommender_precompute_active_days)
      INDEX_BUCKET           = aws_s3_bucket.data.id
      INDEX_KEY              = "recommender/index.npz"
      DEEPSEEK_API_KEY_PARAM = aws_ssm_parameter.deepseek_api_key.name
      LLM_ENABLED            = tostring(var.recommender_llm_enabled)
      LLM_TIMEOUT            = "20"  # limit jednego wywołania DeepSeek (inaczej domyślne 60 s)
      OMP_NUM_THREADS        = "2"
    }
  }

  depends_on = [aws_cloudwatch_log_group.recommender, aws_iam_role_policy.recommender, aws_ecr_repository_policy.recommender]
}

# Wywołania asynchroniczne (EventBridge, liczenie zestawów w tle): bez ponawiania i bez kolejkowania na
# długo - następne i tak przyjdzie za chwilę, a claim liczenia wygasa po 3 min
resource "aws_lambda_function_event_invoke_config" "recommender" {
  function_name                = aws_lambda_function.recommender.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 600
}

resource "aws_apigatewayv2_integration" "recommender" {
  api_id                 = aws_apigatewayv2_api.client.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.recommender.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "recommendations" {
  api_id             = aws_apigatewayv2_api.client.id
  route_key          = "GET /api/recommendations"
  target             = "integrations/${aws_apigatewayv2_integration.recommender.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_lambda_permission" "recommender_api" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.recommender.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.client.execution_arn}/*/*"
}

locals {
  # reguła -> (harmonogram, akcja)
  recommender_schedules = merge(
    {
      refresh    = { expression = "rate(${var.recommender_refresh_minutes} minutes)", action = "refresh" }
      precompute = { expression = var.recommender_precompute_schedule, action = "precompute" }
    },
    var.recommender_keep_warm ? { warmup = { expression = "rate(5 minutes)", action = "warmup" } } : {},
  )
}

resource "aws_cloudwatch_event_rule" "recommender" {
  for_each = local.recommender_schedules

  name                = "${local.name}-recommender-${each.key}"
  schedule_expression = each.value.expression
}

resource "aws_cloudwatch_event_target" "recommender" {
  for_each = local.recommender_schedules

  rule  = aws_cloudwatch_event_rule.recommender[each.key].name
  arn   = aws_lambda_function.recommender.arn
  input = jsonencode({ action = each.value.action })
}

resource "aws_lambda_permission" "recommender_schedule" {
  for_each = local.recommender_schedules

  statement_id  = "AllowEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.recommender.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.recommender[each.key].arn
}
