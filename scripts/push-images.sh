#!/usr/bin/env bash
# Buduje obrazy i wypycha je do ECR (po `terraform apply`).
#   scripts/push-images.sh               # tagger + importer (ECS)
#   scripts/push-images.sh tagger        # tylko tagger (run_task.py + tagger/)
#   scripts/push-images.sh importer      # tylko importer (src/importer)
#   scripts/push-images.sh recommender   # rekomendacje: obraz Lambdy (src/recommender_api + recommender/)
set -euo pipefail
cd "$(dirname "$0")/.."

WHICH=${1:-all}
TAG=${2:-latest}
REGION=$(terraform -chdir=infra output -raw region)
TAGGER_REPO=$(terraform -chdir=infra output -raw worker_repository_url)

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${TAGGER_REPO%%/*}"

# linux/amd64: task definitions są X86_64 (Fargate Spot nie obsługuje ARM64) - ważne na Macu z Apple Silicon
build_push() {
  docker build --platform linux/amd64 -t "$1:$TAG" "$2"
  docker push "$1:$TAG"
}

[[ $WHICH == all || $WHICH == tagger ]] && build_push "$TAGGER_REPO" .
[[ $WHICH == all || $WHICH == importer ]] && build_push "$(terraform -chdir=infra output -raw importer_repository_url)" src/importer

if [[ $WHICH == recommender ]]; then
  # Lambda arm64; bez --provenance=false docker tworzy indeks manifestów, którego Lambda nie przyjmie
  REPO=$(terraform -chdir=infra output -raw recommender_repository_url)
  docker build --platform linux/arm64 --provenance=false -f src/recommender_api/Dockerfile -t "$REPO:$TAG" .
  docker push "$REPO:$TAG"
  # Przy pierwszym wdrożeniu funkcji jeszcze nie ma - tworzy ją dopiero `terraform apply`
  if FUNCTION=$(terraform -chdir=infra output -raw recommender_function 2>/dev/null) && [[ -n $FUNCTION ]]; then
    DIGEST=$(aws ecr describe-images --region "$REGION" --repository-name "${REPO#*/}" --image-ids imageTag="$TAG" \
      --query 'imageDetails[0].imageDigest' --output text)
    aws lambda update-function-code --region "$REGION" --function-name "$FUNCTION" --image-uri "$REPO@$DIGEST" \
      --query 'LastUpdateStatus' --output text
  else
    echo "Teraz: terraform -chdir=infra apply (utworzy Lambdę z tego obrazu)"
  fi
fi
echo "OK"
