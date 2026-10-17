#!/usr/bin/env bash
# Uruchamia jednorazowo task ECS i czeka na jego koniec. Kod wyjścia = kod wyjścia kontenera.
#   scripts/run-task.sh importer    # import teraz, bez czekania na harmonogram (co 2 h)
#   scripts/run-task.sh tagger      # tagowanie teraz, bez czekania na dispatcher
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  # stream logów = <awslogs-stream-prefix>/<nazwa kontenera>/<id taska> (infra/importer.tf, worker.tf)
  importer) FAMILY_OUTPUT=importer_task_family; STREAM_PREFIX=importer/importer ;;
  tagger) FAMILY_OUTPUT=tagger_task_family; STREAM_PREFIX=worker/worker ;;
  *) echo "Użycie: $0 importer|tagger" >&2; exit 2 ;;
esac

out() { terraform -chdir=infra output -raw "$1"; }
export AWS_REGION=$(out region)
CLUSTER=$(out ecs_cluster)
FAMILY=$(out "$FAMILY_OUTPUT")
LOG_GROUP="/ecs/$FAMILY"

# Nie odpalaj drugiego, jeśli już działa (np. tagger uruchomiony przez dispatcher) - poczekaj na niego
TASK=$(aws ecs list-tasks --cluster "$CLUSTER" --family "$FAMILY" --desired-status RUNNING --query 'taskArns[0]' --output text)
if [[ "$TASK" == "None" ]]; then
  # Zwykły Fargate (nie Spot): przy ręcznym uruchomieniu liczy się, żeby wystartował od razu
  TASK=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$FAMILY" --launch-type FARGATE --started-by manual \
    --network-configuration "awsvpcConfiguration={subnets=[$(out task_subnets)],securityGroups=[$(out task_security_group)],assignPublicIp=ENABLED}" \
    --query 'tasks[0].taskArn' --output text)
  echo "Uruchomiono $FAMILY: ${TASK##*/}"
else
  echo "$FAMILY już działa: ${TASK##*/} - czekam na niego"
fi

# `aws ecs wait` poddaje się po 10 min - ponawiamy (do 3 h)
for _ in $(seq 18); do
  aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK" 2>/dev/null && break
  echo "  ... nadal działa ($(date +%H:%M))"
done

read -r STATUS EXIT_CODE REASON < <(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[0].[lastStatus, containers[0].exitCode, stoppedReason]' --output text)
echo "Status: $STATUS, kod wyjścia: $EXIT_CODE ($REASON)"
echo "--- ostatnie logi taska ($LOG_GROUP) ---"
aws logs tail "$LOG_GROUP" --since 3h --format short --log-stream-name-prefix "$STREAM_PREFIX/${TASK##*/}" 2>/dev/null | tail -15 || true

[[ "$STATUS" == "STOPPED" && "$EXIT_CODE" == "0" ]]
