#!/usr/bin/env bash
# Initial load po postawieniu infry: importer -> SQS -> tagger (aż kolejka będzie pusta) -> podsumowanie.
# Wymaga: terraform apply, ustawionych sekretów w SSM i wypchniętych obrazów (scripts/push-images.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

out() { terraform -chdir=infra output -raw "$1"; }
export AWS_REGION=$(out region)
QUEUE=$(out events_queue_url)
DLQ=$(out events_dlq_url)
TABLE=$(terraform -chdir=infra output -json tables | python3 -c 'import json,sys; print(json.load(sys.stdin)["events"])')

depth() {  # widoczne + w trakcie przetwarzania
  aws sqs get-queue-attributes --queue-url "$1" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes.[ApproximateNumberOfMessages, ApproximateNumberOfMessagesNotVisible]' --output text \
    | awk '{print $1 + $2}'
}

echo "== 0. Sekrety w SSM"
for param in "$(out um_api_token_parameter)" "$(out deepseek_api_key_parameter)"; do
  if [[ "$(aws ssm get-parameter --name "$param" --with-decryption --query Parameter.Value --output text)" == "CHANGE_ME" ]]; then
    echo "Parametr $param ma jeszcze wartość CHANGE_ME - ustaw go (README, sekcja Deploy)." >&2
    exit 1
  fi
done
echo "OK"

echo "== 1. Import (pierwszy przebieg: brak stanu w S3, więc wszystkie rekordy idą na kolejkę)"
scripts/run-task.sh importer || echo "!! importer zakończył się błędem - część źródeł mogła się nie zaimportować (logi wyżej)"
echo "W kolejce: $(depth "$QUEUE") wiadomości"

echo "== 2. Tagowanie, aż kolejka będzie pusta"
# Wiadomość, która nie przeszła, wraca po visibility timeout (30 min), a po 5 próbach trafia do DLQ
for round in $(seq 6); do
  left=$(depth "$QUEUE")
  [[ "$left" == "0" ]] && break
  echo "-- runda $round, w kolejce: $left"
  scripts/run-task.sh tagger || echo "!! tagger: część wiadomości nie przeszła, zostały w kolejce"
done

echo "== 3. Podsumowanie"
echo "Kolejka: $(depth "$QUEUE"), DLQ: $(depth "$DLQ")"
echo "Rekordy w $TABLE wg źródła:"
aws dynamodb scan --table-name "$TABLE" --projection-expression "#s" --expression-attribute-names '{"#s":"source"}' --output json \
  | python3 -c 'import json,sys,collections; c=collections.Counter(i["source"]["S"] for i in json.load(sys.stdin)["Items"]); [print(f"  {k}: {v}") for k,v in sorted(c.items())]; print(f"  razem: {sum(c.values())}")'
