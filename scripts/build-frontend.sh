#!/usr/bin/env bash
# Buduje obie aplikacje frontendu (React + TS) do src/frontend/dist - wymagane przed `terraform apply`.
set -euo pipefail
cd "$(dirname "$0")/../src/frontend"
npm ci
npm test
npm run build
