#!/usr/bin/env python3
"""
SQS source — receive raw-event diffs and delete them after processing.

The backend puts diffs on the queue; each message body is a JSON ARRAY
of raw event records (1..N records, same schema as the Warsaw API).

Queue URL: env SQS_QUEUE_URL (or constructor arg).
boto3 picks up credentials automatically (ECS task role). No keys in code.
"""

import json
import logging
import os

import boto3

log = logging.getLogger(__name__)


class SQSSource:
    """Receive batches of raw event records from SQS; delete by receipt handle."""

    def __init__(self, queue_url: str | None = None):
        self.queue_url = queue_url or os.environ["SQS_QUEUE_URL"]
        self.client = boto3.client("sqs")

    def receive(self, max_messages: int = 10) -> list[dict]:
        """Long-poll once and parse each message body.

        Returns [{"raw": <parsed body>, "receipt_handle": str}, ...].

        A body that is not valid JSON or not a list fails ONLY that message:
        it is logged, counted here as a parse failure ("raw": None), and must
        NOT be deleted by the caller — SQS visibility timeout / DLQ handles it.
        """
        resp = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max(1, min(max_messages, 10)),
            WaitTimeSeconds=5,
        )
        out = []
        for msg in resp.get("Messages", []):
            handle = msg["ReceiptHandle"]
            try:
                body = json.loads(msg["Body"])
                if not isinstance(body, list):
                    raise ValueError(
                        f"SQS body is {type(body).__name__}, expected list"
                    )
                out.append({"raw": body, "receipt_handle": handle})
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                log.error(
                    "Unparseable SQS message %s (%s); leaving on queue",
                    msg.get("MessageId"), e,
                )
                out.append({"raw": None, "receipt_handle": handle, "error": str(e)})
        return out

    def delete(self, receipt_handle: str) -> None:
        """Delete a message after its records were successfully written."""
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
        )
