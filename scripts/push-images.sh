#!/usr/bin/env bash
# Buduje obrazy ECS i wypycha je do ECR (po `terraform apply`).
#   scripts/push-images.sh            # oba obrazy
#   scripts/push-images.sh tagger     # tylko tagger (run_task.py + tagger/)
#   scripts/push-images.sh importer   # tylko importer (src/importer)
set -euo pipefail
cd "$(dirname "$0")/.."

WHICH=${1:-all}
TAG=${2:-latest}
REGION=$(terraform -chdir=infra output -raw region)
TAGGER_REPO=$(terraform -chdir=infra output -raw worker_repository_url)
IMPORTER_REPO=$(terraform -chdir=infra output -raw importer_repository_url)

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${TAGGER_REPO%%/*}"

# linux/amd64: task definitions są X86_64 (Fargate Spot nie obsługuje ARM64) - ważne na Macu z Apple Silicon
build_push() {
  docker build --platform linux/amd64 -t "$1:$TAG" "$2"
  docker push "$1:$TAG"
}

[[ $WHICH == all || $WHICH == tagger ]] && build_push "$TAGGER_REPO" .
[[ $WHICH == all || $WHICH == importer ]] && build_push "$IMPORTER_REPO" src/importer
echo "OK"
