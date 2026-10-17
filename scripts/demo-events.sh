#!/usr/bin/env bash
# Wydarzenia demo pod prezentację (src/importer/demo_events.json) w produkcyjnej bazie.
#   scripts/demo-events.sh                            # wysyłka -> tagger -> indeks -> zestawy od nowa
#   scripts/demo-events.sh --start 2026-10-18T14:00   # terminy względem początku prezentacji
#   scripts/demo-events.sh --dry-run                  # tylko podgląd rekordów
#   scripts/demo-events.sh --delete                   # usunięcie wydarzeń demo po prezentacji
# Wymaga python3 z boto3 i credentiali AWS (jak scripts/recommender-refresh.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ " $* " == *" --dry-run "* ]]; then
  exec python3 src/importer/demo.py "$@"
fi

out() { terraform -chdir=infra output -raw "$1"; }
REGION=$(out region)
FUNCTION=$(out recommender_function)
# Nazwy tabel z konfiguracji Lambdy rekomendera (te same, z których czyta)
lambda_env() { aws lambda get-function-configuration --region "$REGION" --function-name "$FUNCTION" --query "Environment.Variables.$1" --output text; }
export AWS_REGION=$REGION AWS_DEFAULT_REGION=$REGION
export SQS_QUEUE_URL=$(out events_queue_url) EVENTS_TABLE=$(lambda_env EVENTS_TABLE) RESULTS_TABLE=$(lambda_env RESULTS_TABLE)

if [[ " $* " == *" --delete "* ]]; then
  python3 src/importer/demo.py --delete
else
  python3 src/importer/demo.py --wait "$@"   # dispatcher uruchamia taggera w ciągu minuty
fi
scripts/recommender-refresh.sh               # indeks z (albo bez) wydarzeń demo
python3 src/importer/demo.py --reset-sets    # zestawy policzą się od nowa przy najbliższym wejściu
echo "Gotowe: odśwież portal (pierwsze wejście liczy zestawy od nowa, kilka-kilkanaście sekund)."
