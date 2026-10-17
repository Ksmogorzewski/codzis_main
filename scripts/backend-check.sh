#!/usr/bin/env bash
# Kontrola backendu w Pythonie (Lambdy API klienta, partnera, dispatcher, warstwa codzis_common):
# lint (ruff), formatowanie (ruff format --check), typy (mypy), testy (pytest).
# Wymaga .venv: python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
set -euo pipefail
cd "$(dirname "$0")/.."

BIN=.venv/bin
if [[ ! -x "$BIN/pytest" ]]; then
  echo "Brak .venv - uruchom: python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
  exit 1
fi

echo "== ruff check"
"$BIN/ruff" check .

echo "== ruff format --check"
"$BIN/ruff" format --check .

# Każda Lambda ma własny moduł `handler`, więc mypy osobno dla każdego katalogu.
echo "== mypy"
for target in src/client_api src/api src/dispatcher tests; do
  "$BIN/mypy" "$target"
done

echo "== pytest"
"$BIN/pytest" -q
