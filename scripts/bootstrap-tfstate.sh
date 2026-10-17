#!/usr/bin/env bash
# Bucket S3 na state Terraforma (lock: plik .tflock w tym samym buckecie, use_lockfile = true).
# Jednorazowo, przed pierwszym `terraform init`. Bezpieczny do ponownego uruchomienia.
#   scripts/bootstrap-tfstate.sh
set -euo pipefail

REGION=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="codzis-tfstate-$ACCOUNT" # musi się zgadzać z backend "s3" w infra/versions.tf

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket $BUCKET już istnieje"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  echo "Utworzono bucket $BUCKET"
fi

# Wersjonowanie = historia state'u (odzyskanie po zepsutym apply)
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled

aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Stare wersje state'u kasujemy po 30 dniach, żeby bucket nie rósł bez końca
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
  '{"Rules":[{"ID":"expire-old-state-versions","Status":"Enabled","Filter":{},"NoncurrentVersionExpiration":{"NoncurrentDays":30}}]}' >/dev/null

echo "Gotowe: s3://$BUCKET"
