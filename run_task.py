#!/usr/bin/env python3
"""
run_task.py — ONE-SHOT ECS task entrypoint.

Control flow:
    1. Receive a batch of messages from SQS (env SQS_QUEUE_URL).
       Each message body is a JSON array of raw event records (a diff).
    2. For each message:
         prepare_records(raw) -> slim records
         tag_events(slim)     -> LLM tags  (tagger / DeepSeek)
         merge(raw, tagged)   -> full record + "id" + "tags" (pure)
         for each merged record:
             skip if sink.exists(record["id"])
             else sink.put(sanitize(record))
         source.delete(receipt_handle)   # ONLY after the whole message succeeded
    3. Repeat until a receive returns 0 messages (or --max-batches hit),
       then exit.

Exit code is the ONLY "task ended" signal:
    0 = everything succeeded, 1 = any failure.

Env:
    SQS_QUEUE_URL   (required)  source queue
    DYNAMODB_TABLE  (optional, default "warsaw_events" + warning)
    AWS_REGION      (optional, default "eu-central-1")
    DEEPSEEK_API_KEY (required by tagger.client, via env or .env)

Usage:
    python3 run_task.py [--max-batches N]
"""

import argparse
import logging
import sys

from tagger import merge, tag_events
from tagger.dynamodb_sink import DynamoDBSink, sanitize
from tagger.prepare import prepare_records
from tagger.sqs_source import SQSSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run_task")


def main() -> int:
    ap = argparse.ArgumentParser(description="One-shot SQS -> tag -> DynamoDB task.")
    ap.add_argument(
        "--max-batches",
        type=int,
        default=100,
        help="loop guard: stop after N receive passes even if the queue "
             "never drains (default 100)",
    )
    args = ap.parse_args()

    all_ok = True
    written = skipped = failed_msgs = 0

    source = SQSSource()
    sink = DynamoDBSink()

    for batch_no in range(1, args.max_batches + 1):
        try:
            messages = source.receive(max_messages=10)
        except Exception as e:
            log.error("SQS receive failed on batch %d: %s", batch_no, e)
            all_ok = False
            break

        if not messages:
            log.info("Queue drained (batch %d empty) — done.", batch_no)
            break

        log.info("Batch %d: received %d message(s)", batch_no, len(messages))

        for msg in messages:
            handle = msg["receipt_handle"]
            raw_events = msg["raw"]

            if raw_events is None:
                # Body was not valid JSON / not a list: already logged by the
                # source. Do NOT delete — count as failure, move on.
                log.error("Skipping unparseable message (handle=%.20s...)", handle)
                all_ok = False
                failed_msgs += 1
                continue

            try:
                slim = prepare_records(raw_events)
                summary = tag_events(slim)
                tagged = summary["results"]          # {id: dims}
                merged = merge(raw_events, tagged)   # full record + id + tags

                for record in merged:
                    if sink.exists(record["id"]):
                        skipped += 1
                        continue
                    sink.put(sanitize(record))       # raises on failure
                    written += 1

                source.delete(handle)                # only after success
                log.info(
                    "Message processed: %d record(s) (%d new, %d existing) "
                    "— deleted from queue",
                    len(merged), written, skipped,
                )
            except Exception as e:
                # Do NOT delete the message: SQS visibility timeout will
                # redeliver it (or the DLQ will catch it after max receives).
                log.error("Message failed (kept on queue): %s", e, exc_info=True)
                all_ok = False
                failed_msgs += 1
    else:
        log.error("Hit --max-batches=%d without draining the queue",
                  args.max_batches)
        all_ok = False

    log.info(
        "Finished: %d written, %d skipped (already existed), %d failed message(s)",
        written, skipped, failed_msgs,
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
