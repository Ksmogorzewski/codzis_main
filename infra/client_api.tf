# API portalu klienta: HTTP API + JWT authorizer (Cognito) -> Lambda -> tabela users
# (+ odczyt codzis-events, zapisy na wydarzenia, liczniki, znajomi i czat ekipy: infra/community.tf).

# Profile klientów pod rekomendacje (RAG): odpowiedzi z onboardingu, preferencje, profil tekstowy
resource "aws_dynamodb_table" "users" {
  name         = "${local.name}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId" # sub z Cognito

  attribute {
    name = "userId"
    type = "S"
  }

  # Dane, których nie da się odtworzyć - kopia z ostatnich 35 dni (grosze przy tej skali)
  point_in_time_recovery {
    enabled = true
  }
}

data "archive_file" "client_api" {
  type        = "zip"
  source_dir  = "${path.module}/../src/client_api"
  output_path = "${path.module}/build/client_api.zip"
  excludes    = ["__pycache__", "**/__pycache__"]
}

resource "aws_cloudwatch_log_group" "client_api" {
  name              = "/aws/lambda/${local.name}-client-api"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "client_api" {
  name = "${local.name}-client-api"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "client_api" {
  name = "${local.name}-client-api"
  role = aws_iam_role.client_api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.client_api.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.users.arn
      },
      {
        # Eksploruj i Popularne: scan z pamięcią w Lambdzie (5 min), szczegóły i zapis po kluczu
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.events.arn
      },
      {
        # Zapisy na wydarzenia (Put/Delete także w TransactWriteItems), lista zapisanych, "moje zapisy" (GSI byUser)
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query"]
        Resource = [aws_dynamodb_table.attendance.arn, "${aws_dynamodb_table.attendance.arn}/index/*"]
      },
      {
        # Liczniki zapisanych (Update także w TransactWriteItems) i top po liczbie zapisanych
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:BatchGetItem", "dynamodb:Query"]
        Resource = [aws_dynamodb_table.event_stats.arn, "${aws_dynamodb_table.event_stats.arn}/index/*"]
      },
      {
        # Znajomi: kody, zaproszenia, znajomości, limit złych kodów (Put/Delete/ConditionCheck także w TransactWriteItems)
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:UpdateItem", "dynamodb:Query",
          "dynamodb:ConditionCheckItem",
        ]
        Resource = aws_dynamodb_table.friends.arn
      },
      {
        # Czat ekipy: ekipy, członkowie, wiadomości, plakietki (Put/Update/Delete także w TransactWriteItems)
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:UpdateItem", "dynamodb:Query",
          "dynamodb:BatchGetItem",
        ]
        Resource = aws_dynamodb_table.crews.arn
      },
      {
        # Po zapisaniu profilu i przy logowaniu: przeliczenie rekomendacji w tle
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.recommender.arn
      },
      {
        # Zdjęcia profilowe (src/client_api/account.py): presigned POST, sprawdzenie uploadu, usunięcie starego
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.photos.arn}/photos/avatars/*"
      },
    ]
  })
}

resource "aws_lambda_function" "client_api" {
  function_name    = "${local.name}-client-api"
  role             = aws_iam_role.client_api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.client_api.output_path
  source_code_hash = data.archive_file.client_api.output_base64sha256
  layers           = [aws_lambda_layer_version.common.arn, local.powertools_layer_arn]
  memory_size      = 512 # pamięć podręczna wydarzeń (scan codzis-events) dla Eksploruj i Popularnych
  timeout          = 10

  environment {
    variables = {
      USERS_TABLE          = aws_dynamodb_table.users.name
      DISTRICTS            = jsonencode(local.warsaw_districts)
      RECOMMENDER_FUNCTION = aws_lambda_function.recommender.function_name
      EVENTS_TABLE         = aws_dynamodb_table.events.name
      ATTENDANCE_TABLE     = aws_dynamodb_table.attendance.name
      STATS_TABLE          = aws_dynamodb_table.event_stats.name
      FRIENDS_TABLE        = aws_dynamodb_table.friends.name
      CREWS_TABLE          = aws_dynamodb_table.crews.name
      # zdjęcia profilowe w buckecie zdjęć ogłoszeń, serwowane przez CloudFront panelu pod /photos/*
      PHOTOS_BUCKET   = aws_s3_bucket.photos.id
      PHOTOS_BASE_URL = local.website_origin
      # pole "service" w logach JSON (Powertools Logger)
      POWERTOOLS_SERVICE_NAME = "${local.name}-client-api"
    }
  }

  depends_on = [aws_cloudwatch_log_group.client_api, aws_iam_role_policy.client_api]
}

resource "aws_apigatewayv2_api" "client" {
  name          = "${local.name}-client-api"
  protocol_type = "HTTP"

  # Strona woła API bezpośrednio (inna domena niż strona) - CORS obsługuje API Gateway
  cors_configuration {
    allow_origins = concat(local.client_origins, var.client_dev_origins)
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }
}

# Weryfikacja ID tokenu Cognito (podpis, wystawca, aud = klient web) jeszcze przed Lambdą
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.client.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = "https://${aws_cognito_user_pool.clients.endpoint}"
    audience = [aws_cognito_user_pool_client.web.id]
  }
}

resource "aws_apigatewayv2_integration" "client_api" {
  api_id                 = aws_apigatewayv2_api.client.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.client_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "client" {
  for_each = toset([
    "GET /api/me",
    "PUT /api/me",
    "POST /api/me/photo",
    "PUT /api/me/photo",
    "DELETE /api/me/photo",
    "GET /api/onboarding",
    "PUT /api/profile",
    "GET /api/events",
    "GET /api/events/stats",
    "GET /api/events/{id}",
    "PUT /api/events/{id}/save",
    "DELETE /api/events/{id}/save",
    "GET /api/events/{id}/attendees",
    "GET /api/popular",
    "GET /api/me/events",
    "GET /api/friends",
    "POST /api/friends/code",
    "GET /api/friends/code/{code}",
    "POST /api/friends/invite",
    "PUT /api/friends/requests/{userId}",
    "DELETE /api/friends/requests/{userId}",
    "DELETE /api/friends/{userId}",
    "GET /api/friends/going",
    "GET /api/events/{id}/crew",
    "POST /api/events/{id}/crew/messages",
    "GET /api/me/crews",
  ])

  api_id             = aws_apigatewayv2_api.client.id
  route_key          = each.key
  target             = "integrations/${aws_apigatewayv2_integration.client_api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "client" {
  api_id      = aws_apigatewayv2_api.client.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 10
    throttling_burst_limit = 20
  }
}

resource "aws_lambda_permission" "client_api" {
  statement_id  = "AllowHttpApiInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.client_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.client.execution_arn}/*/*"
}
