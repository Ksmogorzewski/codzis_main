#!/usr/bin/env bash
# Przebudowa indeksu rekomendacji od razu (normalnie robi to EventBridge co 30 min).
# Pierwsze uruchomienie liczy embeddingi wszystkich eventów (~1-3 min), kolejne tylko nowych.
#   scripts/recommender-refresh.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REGION=$(terraform -chdir=infra output -raw region)
FUNCTION=$(terraform -chdir=infra output -raw recommender_function)
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

STATUS=$(aws lambda invoke --region "$REGION" --function-name "$FUNCTION" \
  --cli-binary-format raw-in-base64-out --payload '{"action":"refresh"}' \
  --cli-read-timeout 900 --query 'FunctionError' --output text "$OUT")
cat "$OUT"; echo
[[ $STATUS == None ]] || { echo "Błąd funkcji - logi: aws logs tail /aws/lambda/$FUNCTION --region $REGION" >&2; exit 1; }
