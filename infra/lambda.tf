data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${path.module}/../src/api"
  output_path = "${path.module}/build/api.zip"
  excludes    = ["__pycache__", "**/__pycache__"]
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "api" {
  name = "${local.name}-api"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api" {
  name = "${local.name}-api"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query"]
        Resource = flatten([
          for t in [aws_dynamodb_table.submissions, aws_dynamodb_table.partners, aws_dynamodb_table.payments] :
          [t.arn, "${t.arn}/index/*"]
        ])
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.events.arn
      },
      {
        # Wymagane, żeby presigned POST podpisany rolą Lambdy był ważny
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.photos.arn}/photos/*"
      },
    ]
  })
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  layers           = [aws_lambda_layer_version.common.arn, local.powertools_layer_arn]
  memory_size      = 128
  timeout          = 10

  environment {
    variables = {
      SUBMISSIONS_TABLE  = aws_dynamodb_table.submissions.name
      EVENTS_QUEUE_URL   = aws_sqs_queue.events.url
      PARTNERS_TABLE     = aws_dynamodb_table.partners.name
      PAYMENTS_TABLE     = aws_dynamodb_table.payments.name
      PHOTOS_BUCKET      = aws_s3_bucket.photos.id
      MAX_PHOTO_BYTES    = tostring(var.max_photo_mb * 1024 * 1024)
      EVENT_COST_CREDITS = tostring(var.event_cost_credits)
      STARTER_CREDITS    = tostring(var.starter_credits)
      CREDIT_PACKAGES    = jsonencode(var.credit_packages)
      CURRENCY           = var.currency
      CATEGORIES         = jsonencode(var.event_categories)
      DISTRICTS          = jsonencode(local.warsaw_districts)
      PUBLIC_BASE_URL    = local.website_origin
      # apiKeyId -> nazwa partnera
      PARTNERS = jsonencode({ for name, key in aws_api_gateway_api_key.partner : key.id => name })
      # pole "service" w logach JSON (Powertools Logger)
      POWERTOOLS_SERVICE_NAME = "${local.name}-api"
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*/*"
}
