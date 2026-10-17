#!/usr/bin/env bash
# Buduje obraz taggera (Dockerfile w katalogu głównym) i wypycha go do ECR (po `terraform apply`).
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=$(terraform -chdir=infra output -raw worker_repository_url)
REGION=$(terraform -chdir=infra output -raw region)
TAG=${1:-latest}

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
# linux/amd64: Fargate Spot nie obsługuje ARM64 (ważne przy budowaniu na Macu z Apple Silicon)
docker build --platform linux/amd64 -t "$REPO:$TAG" .
docker push "$REPO:$TAG"
