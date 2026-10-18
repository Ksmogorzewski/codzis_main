# Logowanie organizatorów (panel partnera) przez Google: osobna pula Cognito, tylko Google, samoobsługa
# (pierwsze logowanie + GET /me zakłada konto organizatora; partnerId = sub, nazwa = imię i nazwisko z Google).
# Osobna pula, bo autoryzator REST API przepuszcza każdy token swojej puli - token z portalu klienta
# nie otworzy API partnera. Włącza się razem z Google dla klientów (ten sam klient OAuth Google);
# bez sekretu Google (client_auth.tf) panel loguje jak dotąd kluczem API (api.tf).
resource "aws_cognito_user_pool" "partners" {
  count = local.google_enabled ? 1 : 0

  name                = "${local.name}-partners"
  deletion_protection = "INACTIVE"
}

# Hosted UI: https://<prefix>.auth.<region>.amazoncognito.com (tu przekierowuje logowanie przez Google)
resource "aws_cognito_user_pool_domain" "partners" {
  count = local.google_enabled ? 1 : 0

  domain                = var.partner_cognito_domain_prefix
  user_pool_id          = aws_cognito_user_pool.partners[0].id
  managed_login_version = 1
}

resource "aws_cognito_identity_provider" "partner_google" {
  count = local.google_enabled ? 1 : 0

  user_pool_id     = aws_cognito_user_pool.partners[0].id
  provider_name    = "Google"
  provider_type    = "Google"
  provider_details = local.google_provider_details

  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
    name           = "name" # imię i nazwisko = nazwa organizatora (podpis ogłoszeń w portalu)
    username       = "sub"
  }
}

resource "aws_cognito_user_pool_client" "partner_web" {
  count = local.google_enabled ? 1 : 0

  name         = "${local.name}-partner-web"
  user_pool_id = aws_cognito_user_pool.partners[0].id

  # Klient publiczny (SPA): bez sekretu. Tylko Google i odświeżanie tokenów - bez logowania hasłem,
  # więc konta założone z pominięciem Google (API SignUp) i tak nie dostaną tokenów.
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = local.partner_app_urls
  logout_urls                          = local.partner_app_urls
  supported_identity_providers         = ["Google"]

  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 30

  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_identity_provider.partner_google]
}

# Autoryzator REST API: ID token puli partnerów w nagłówku X-Id-Token. Nie Authorization, bo CloudFront
# przed API (cdn.tf) zdejmuje go z GET-ów, a zwykłe nagłówki przepuszcza (jak wcześniej x-api-key).
resource "aws_api_gateway_authorizer" "partners" {
  count = local.google_enabled ? 1 : 0

  name            = "${local.name}-partners"
  rest_api_id     = aws_api_gateway_rest_api.api.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [aws_cognito_user_pool.partners[0].arn]
  identity_source = "method.request.header.X-Id-Token"
}
