import logging
import os

import boto3

QUEUE_URL = os.environ["EVENTS_QUEUE_URL"]
CLUSTER = os.environ["CLUSTER"]
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ["SUBNETS"].split(",")
SECURITY_GROUP = os.environ["SECURITY_GROUP"]

log = logging.getLogger()
log.setLevel(logging.INFO)

sqs = boto3.client("sqs")
ecs = boto3.client("ecs")


def handler(event, context):
    """Wywoływany z EventBridge z {"minMessages": N}. Uruchamia jeden task workera, jeśli trzeba."""
    min_messages = int(event.get("minMessages", 1))

    attrs = sqs.get_queue_attributes(QueueUrl=QUEUE_URL, AttributeNames=["ApproximateNumberOfMessages"])
    waiting = int(attrs["Attributes"]["ApproximateNumberOfMessages"])
    if waiting < min_messages:
        log.info("W kolejce %d < %d, nic do zrobienia", waiting, min_messages)
        return {"started": False, "waiting": waiting}

    # desiredStatus=RUNNING obejmuje też taski PENDING (w trakcie startu)
    running = ecs.list_tasks(cluster=CLUSTER, family=TASK_DEFINITION, desiredStatus="RUNNING")["taskArns"]
    if running:
        log.info("Worker już działa (%s), w kolejce %d", running[0], waiting)
        return {"started": False, "waiting": waiting}

    task_arn = _run_task("FARGATE_SPOT") or _run_task("FARGATE")
    log.info("W kolejce %d, uruchomiono %s", waiting, task_arn)
    return {"started": bool(task_arn), "waiting": waiting, "task": task_arn}


def _run_task(capacity_provider):
    resp = ecs.run_task(
        cluster=CLUSTER,
        taskDefinition=TASK_DEFINITION,
        count=1,
        startedBy="dispatcher",
        capacityProviderStrategy=[{"capacityProvider": capacity_provider, "weight": 1}],
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": [SECURITY_GROUP],
                "assignPublicIp": "ENABLED",  # bez NAT Gateway
            }
        },
    )
    if resp["failures"]:
        # Np. chwilowy brak mocy Spot - wtedy próbujemy zwykłego Fargate
        log.warning("RunTask na %s nie powiódł się: %s", capacity_provider, resp["failures"])
        return None
    return resp["tasks"][0]["taskArn"]
