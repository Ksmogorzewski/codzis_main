#!/usr/bin/env bash
# Zdjęcia wszystkich wydarzeń z tabeli do standardu (tagger/images.py: WebP 1200x800 w buckecie zdjęć) - jednorazowo
# po wdrożeniu i po każdej zmianie standardu (nowy VERSION). Nowe i zmienione wydarzenia przelicza sam tagger przy
# zapisie; ten przebieg dogania to, co już leży w codzis-events. Można go powtarzać: gotowe pliki są pomijane,
# ponawia się tylko to, co się nie udało (kod wyjścia 2 = część zdjęć zostaje źródłowa, np. 404 u źródła).
# Lokalnie (Docker, kod taggera) z twoimi credentialami AWS, jak scripts/import-local.sh.
#   scripts/resize-images.sh              # wszystkie wydarzenia
#   scripts/resize-images.sh --dry-run    # tylko pobranie i przeliczenie (rozmiary w logu), bez zapisu
#   scripts/resize-images.sh --limit 20   # pierwsze 20 wydarzeń ze zdjęciem
set -euo pipefail
cd "$(dirname "$0")/.."

out() { terraform -chdir=infra output -raw "$1"; }
REGION=$(out region)
TABLE=$(terraform -chdir=infra output -json tables | python3 -c 'import json,sys; print(json.load(sys.stdin)["events"])')

# Obraz taggera w natywnej architekturze (bez emulacji amd64 przeliczanie jest kilka razy szybsze)
docker build -q -t codzis-tagger:local . >/dev/null

# Tymczasowe credentiale z bieżącego profilu AWS (działa też z SSO / assume-role)
docker run --rm \
  --env-file <(aws configure export-credentials --format env-no-export) \
  -e AWS_REGION="$REGION" -e AWS_DEFAULT_REGION="$REGION" \
  -e DYNAMODB_TABLE="$TABLE" -e PHOTOS_BUCKET="$(out photos_bucket)" -e PHOTOS_BASE_URL="$(out portal_url)" \
  --entrypoint python codzis-tagger:local -m tagger.images "$@"
