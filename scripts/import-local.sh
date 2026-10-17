#!/usr/bin/env bash
# Uruchamia importer lokalnie (Docker), z twoimi credentialami AWS.
# Potrzebne, bo dane.um.warszawa.pl odrzuca połączenia z adresów IP AWS (timeout na TCP),
# a z polskiego łącza działa. Zapis do S3/SQS jak w ECS; tagger w AWS rusza sam (dispatcher).
#   scripts/import-local.sh            # import
#   scripts/import-local.sh --dry-run  # tylko pobranie + mapowanie
set -euo pipefail
cd "$(dirname "$0")/.."

out() { terraform -chdir=infra output -raw "$1"; }
REGION=$(out region)
TOKEN=$(aws ssm get-parameter --region "$REGION" --name "$(out um_api_token_parameter)" --with-decryption --query Parameter.Value --output text)

docker build -q --platform linux/amd64 -t codzis-importer:local src/importer >/dev/null

# Tymczasowe credentiale z bieżącego profilu AWS (działa też z SSO / assume-role)
docker run --rm --platform linux/amd64 \
  --env-file <(aws configure export-credentials --format env-no-export) \
  -e AWS_REGION="$REGION" -e AWS_DEFAULT_REGION="$REGION" \
  -e SQS_QUEUE_URL="$(out events_queue_url)" -e DATA_BUCKET="$(out data_bucket)" \
  -e UM_API_TOKEN="$TOKEN" \
  codzis-importer:local "$@"
