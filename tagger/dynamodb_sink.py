#!/usr/bin/env python3
"""
DynamoDB sink — all DynamoDB write logic for the tagging pipeline.

boto3 picks up credentials automatically (ECS task role, instance
profile, or ~/.aws). No keys in code.

Table name: env DYNAMODB_TABLE (fallback "warsaw_events" + warning).
Region:     env AWS_REGION     (fallback "eu-central-1").

Duplicate policy: check `exists(event_id)` (GetItem) before `put(item)`
(PutItem) — records whose id is already in the table are skipped.
"""

import logging
import os
from decimal import Decimal

import boto3

log = logging.getLogger(__name__)

DEFAULT_TABLE = "warsaw_events"
DEFAULT_REGION = "eu-central-1"


def sanitize(value):
    """Recursively make a value DynamoDB-safe. Returns None to signal 'drop'.

    - null values       -> dropped (DynamoDB rejects null attributes)
    - float numbers     -> Decimal (DynamoDB numbers must be Decimal, not float)
    - empty strings     -> dropped (noise)
    - empty lists/dicts -> dropped (noise)
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value if value != "" else None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            cleaned = sanitize(v)
            if cleaned is not None:
                out[k] = cleaned
        return out if out else None
    if isinstance(value, list):
        out = []
        for v in value:
            cleaned = sanitize(v)
            if cleaned is not None:
                out.append(cleaned)
        return out if out else None
    return value


class DynamoDBSink:
    """Write tagged event records to a DynamoDB table (skip existing ids)."""

    def __init__(self, table_name: str | None = None, region: str | None = None):
        if table_name is None:
            table_name = os.environ.get("DYNAMODB_TABLE")
            if not table_name:
                table_name = DEFAULT_TABLE
                log.warning(
                    "DYNAMODB_TABLE not set; falling back to placeholder %r",
                    table_name,
                )
        if region is None:
            region = os.environ.get("AWS_REGION", DEFAULT_REGION)
        self.table_name = table_name
        self.region = region
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def exists(self, event_id: str) -> bool:
        """True if an item with this id already exists in the table."""
        resp = self.table.get_item(Key={"id": event_id})
        return "Item" in resp

    def get(self, event_id: str, attributes=("contentHash", "tagInputHash", "tags")) -> dict | None:
        """Fetch selected attributes of an existing item (None if absent)."""
        names = {f"#a{i}": a for i, a in enumerate(attributes)}
        resp = self.table.get_item(
            Key={"id": event_id},
            ProjectionExpression=", ".join(names),
            ExpressionAttributeNames=names,
        )
        return resp.get("Item")

    def put(self, item: dict) -> None:
        """Write one item. The caller should `sanitize` it first.

        Raises on failure (botocore.exceptions.ClientError) — the caller
        treats that as a batch failure and does NOT delete the SQS message.
        """
        self.table.put_item(Item=item)


class SubmissionStatus:
    """Mark partner submissions (portal's "Moje ogłoszenia") as published.

    Table name: env SUBMISSIONS_TABLE. If unset, this is a no-op, so the task
    still works for public-API-only setups.
    """

    def __init__(self, table_name: str | None = None, region: str | None = None):
        table_name = table_name or os.environ.get("SUBMISSIONS_TABLE")
        region = region or os.environ.get("AWS_REGION", DEFAULT_REGION)
        self.table = (
            boto3.resource("dynamodb", region_name=region).Table(table_name)
            if table_name else None
        )

    def published(self, event_id: str, tags: dict | None) -> None:
        if self.table is None:
            return
        values = {":published": "published"}
        update = "SET #status = :published"
        if tags:
            update += ", tags = :tags"
            values[":tags"] = sanitize(tags)
        self.table.update_item(
            Key={"id": event_id},
            UpdateExpression=update,
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
        )
