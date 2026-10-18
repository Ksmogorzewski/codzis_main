# Logowanie klientów: Cognito User Pool.
#   - e-mail + hasło: własny formularz strony, wywołania API Cognito wprost z przeglądarki (USER_PASSWORD_AUTH)
#   - Google (domyślnie wyłączone): Hosted UI Cognito (kod autoryzacyjny + PKCE). Włącza się samo, gdy
#     pojawi się google_client_id/secret (infra/secrets.auto.tfvars) - wtedy powstaje też domena Hosted UI
#     i ustawienia OAuth. Ten sam klient OAuth Google loguje organizatorów (osobna pula: partner_auth.tf).
resource "aws_cognito_user_pool" "clients" {
  name                     = "${local.name}-clients"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE"

  username_configuration {
    case_sensitive = false
  }

  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_uppercase                = false
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Domyślna wysyłka Cognito: limit ~50 e-maili dziennie, na PoC wystarcza
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "WarsawNow – kod weryfikacyjny"
    email_message        = "Twój kod do WarsawNow: {####}"
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }
}

# Hosted UI: https://<prefix>.auth.<region>.amazoncognito.com (tu przekierowuje logowanie przez Google)
resource "aws_cognito_user_pool_domain" "clients" {
  count = local.google_enabled ? 1 : 0

  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.clients.id
  # 1 = klasyczny Hosted UI; wersja 2 (managed login) wymaga osobnej konfiguracji brandingu
  managed_login_version = 1
}

locals {
  # Klient OAuth "Web application" z Google Cloud Console, redirect URIs: terraform output google_oauth_redirect_uris.
  # Pełny zestaw kluczy, które Cognito i tak ustawia dla Google - bez tego Terraform pokazuje stałą różnicę.
  google_provider_details = {
    client_id                     = var.google_client_id
    client_secret                 = var.google_client_secret
    authorize_scopes              = "openid email profile"
    attributes_url                = "https://people.googleapis.com/v1/people/me?personFields="
    attributes_url_add_attributes = "true"
    authorize_url                 = "https://accounts.google.com/o/oauth2/v2/auth"
    oidc_issuer                   = "https://accounts.google.com"
    token_request_method          = "POST"
    token_url                     = "https://www.googleapis.com/oauth2/v4/token"
  }
}

resource "aws_cognito_identity_provider" "google" {
  count = local.google_enabled ? 1 : 0

  user_pool_id     = aws_cognito_user_pool.clients.id
  provider_name    = "Google"
  provider_type    = "Google"
  provider_details = local.google_provider_details

  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
    # Atrybut "name" to w portalu samo imię (pole „Imię” przy rejestracji, widoczne na listach zapisanych);
    # nazwisko i zdjęcie wypełniają profil przy pierwszym logowaniu (src/client_api/account.py)
    name        = "given_name"
    family_name = "family_name"
    picture     = "picture"
    username    = "sub"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name}-web"
  user_pool_id = aws_cognito_user_pool.clients.id

  # Klient publiczny (SPA): bez sekretu
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  # OAuth (Hosted UI) tylko dla logowania Google; e-mail + hasło go nie potrzebuje
  allowed_oauth_flows_user_pool_client = local.google_enabled
  allowed_oauth_flows                  = local.google_enabled ? ["code"] : null
  # aws.cognito.signin.user.admin: konto Google bez imienia uzupełnia je w portalu (UpdateUserAttributes)
  allowed_oauth_scopes         = local.google_enabled ? ["openid", "email", "profile", "aws.cognito.signin.user.admin"] : null
  callback_urls                = local.google_enabled ? local.client_app_urls : null
  logout_urls                  = local.google_enabled ? local.client_app_urls : null
  supported_identity_providers = local.google_enabled ? ["COGNITO", "Google"] : ["COGNITO"]

  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 30

  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_identity_provider.google]
}
