#!/usr/bin/env bash
# Lokalny development frontendu z konfiguracją z wdrożonej infry (terraform output).
#   scripts/frontend-dev.sh client    # http://localhost:8000 - jest na liście adresów powrotu Cognito i w CORS API
#   scripts/frontend-dev.sh partner   # http://localhost:8001 - /api przez proxy Vite do domeny panelu
set -euo pipefail
cd "$(dirname "$0")/.."

APP=${1:-client}
case "$APP" in
  client) OUTPUT=client_app_config ;;
  partner) OUTPUT=partner_app_config ;;
  *) echo "Użycie: $0 client|partner" >&2; exit 2 ;;
esac

# config.js tylko lokalnie (gitignored); na S3 trafia wersja z Terraforma
echo "window.APP_CONFIG = $(terraform -chdir=infra output -json "$OUTPUT");" > "src/frontend/$APP/public/config.js"
[[ -d src/frontend/node_modules ]] || npm --prefix src/frontend ci
if [[ "$APP" == partner ]]; then
  export PARTNER_ORIGIN=$(terraform -chdir=infra output -raw portal_url)
fi
npm --prefix src/frontend run "dev:$APP"
