# API portalu klienta: HTTP API + JWT authorizer (Cognito) -> Lambda -> tabela users.

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
  excludes    = ["__pycache__"]
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
        # Po zapisaniu profilu i przy logowaniu: przeliczenie rekomendacji w tle
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.recommender.arn
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
  layers           = [aws_lambda_layer_version.common.arn]
  memory_size      = 128
  timeout          = 10

  environment {
    variables = {
      USERS_TABLE          = aws_dynamodb_table.users.name
      DISTRICTS            = jsonencode(local.warsaw_districts)
      RECOMMENDER_FUNCTION = aws_lambda_function.recommender.function_name
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
    allow_methods = ["GET", "PUT", "OPTIONS"]
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
  for_each = toset(["GET /api/me", "GET /api/onboarding", "PUT /api/profile"])

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
