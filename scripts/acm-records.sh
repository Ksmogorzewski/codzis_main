#!/usr/bin/env bash
# Rekordy walidacyjne certyfikatu portalu (do wpisania w home.pl), prosto z AWS.
# Działa także w trakcie `terraform apply`, kiedy apply czeka na wydanie certyfikatu.
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN=$(sed -n 's/^domain_name *= *"\(.*\)"/\1/p' infra/terraform.tfvars)
ARN=$(aws acm list-certificates --region us-east-1 --certificate-statuses PENDING_VALIDATION ISSUED \
  --query "reverse(sort_by(CertificateSummaryList[?DomainName=='$DOMAIN'], &CreatedAt))[0].CertificateArn" --output text)
if [[ -z "$ARN" || "$ARN" == "None" ]]; then
  echo "Brak certyfikatu dla $DOMAIN (jeszcze nie utworzony?)" >&2
  exit 1
fi

# W home.pl (strefa waw-out.pl) w polu Host wpisz część PRZED ".waw-out.pl", np. "_abc123.partner"
aws acm describe-certificate --region us-east-1 --certificate-arn "$ARN" \
  --query 'Certificate.DomainValidationOptions[].[DomainName, ValidationStatus, ResourceRecord.Type, ResourceRecord.Name, ResourceRecord.Value]' \
  --output table
