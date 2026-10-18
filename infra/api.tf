# REST API (v1) - tylko ono obsługuje API keys + usage plans.
# Ruch z przeglądarki idzie przez CloudFront (ta sama domena), więc bez CORS.
# Logowanie: z Google (sekret codzis/google-oauth, client_auth.tf) token Cognito puli partnerów (partner_auth.tf), bez Google klucz API.
resource "aws_api_gateway_rest_api" "api" {
  name = "${local.name}-api"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# Cały routing robi Lambda: /{proxy+} ANY, zawsze z tokenem Google albo kluczem API.
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.proxy.id
  http_method      = "ANY"
  authorization    = local.google_enabled ? "COGNITO_USER_POOLS" : "NONE"
  authorizer_id    = local.google_enabled ? aws_api_gateway_authorizer.partners[0].id : null
  api_key_required = !local.google_enabled
}

resource "aws_api_gateway_integration" "proxy" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy,
      aws_api_gateway_method.proxy,
      aws_api_gateway_integration.proxy,
      aws_api_gateway_authorizer.partners,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Nazwa stage'a = prefiks ścieżki w CloudFront (https://domena/api/...).
resource "aws_api_gateway_stage" "api" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = "api"
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.api.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.api_rate_limit
    throttling_burst_limit = var.api_burst_limit
  }
}

# Jeden klucz na partnera - to jest jego "login" do portalu, dopóki nie ma logowania Google.
resource "aws_api_gateway_api_key" "partner" {
  for_each = var.partners

  name = "${local.name}-${each.key}"
}

resource "aws_api_gateway_usage_plan" "partners" {
  name = "${local.name}-partners"

  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.api.stage_name
  }

  # Limity per klucz
  throttle_settings {
    rate_limit  = var.api_rate_limit
    burst_limit = var.api_burst_limit
  }

  quota_settings {
    limit  = var.api_daily_quota
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "partner" {
  for_each = var.partners

  key_id        = aws_api_gateway_api_key.partner[each.key].id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.partners.id
}
