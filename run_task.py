#!/usr/bin/env python3
"""
run_task.py — ONE-SHOT ECS task entrypoint.

Control flow:
    1. Receive a batch of messages from SQS (env SQS_QUEUE_URL).
       Each message body is a JSON array of raw event records (a diff).
    2. For each message:
         normalize(raw)       -> id, source, startsAt/endsAt, Warsaw API quirks
         skip records already in the table (BEFORE tagging - saves tokens)
         prepare_records(new) -> slim records
         tag_events(slim)     -> LLM tags  (tagger / DeepSeek)
         merge(new, tagged)   -> full record + "id" + "tags" (pure)
         sink.put(sanitize(record)) for every TAGGED record
         partner records: mark submission as published (portal status)
         source.delete(receipt_handle)   # ONLY if every record got tags;
                                         # otherwise redelivery re-tags just the rest
    3. Repeat until a receive returns 0 messages (or --max-batches hit),
       then exit.

Exit code is the ONLY "task ended" signal:
    0 = everything succeeded, 1 = any failure.

Env:
    SQS_QUEUE_URL   (required)  source queue
    DYNAMODB_TABLE  (optional, default "warsaw_events" + warning)
    SUBMISSIONS_TABLE (optional) partner portal submissions; no-op if unset
    AWS_REGION      (optional, default "eu-central-1")
    DEEPSEEK_API_KEY (required by tagger.client, via env or .env)

Usage:
    python3 run_task.py [--max-batches N]
"""

import argparse
import logging
import os
import sys
import tempfile

from tagger import merge, tag_events
from tagger.client import resolve_api_key
from tagger.dynamodb_sink import DynamoDBSink, SubmissionStatus, sanitize
from tagger.normalize import SOURCE_PARTNER, normalize
from tagger.prepare import prepare_records
from tagger.sqs_source import SQSSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run_task")

# Orchestrator writes per-event results to a file; the container's /app is read-only.
TAGGED_PATH = os.path.join(tempfile.gettempdir(), "tagged.jsonl")


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

    # Fail fast before touching the queue: without a key every message would
    # fail 5 times and end up in the DLQ.
    try:
        if resolve_api_key() == "CHANGE_ME":
            raise RuntimeError("DEEPSEEK_API_KEY is still the Terraform placeholder (set it in SSM)")
    except RuntimeError as e:
        log.error("%s", e)
        return 1

    all_ok = True
    written = skipped = failed_msgs = 0

    source = SQSSource()
    sink = DynamoDBSink()
    submissions = SubmissionStatus()

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
                records = []
                for raw in raw_events:
                    try:
                        records.append(normalize(raw))
                    except ValueError as e:
                        log.error("Dropping invalid record (%s): %.80s", e, raw)

                new = []
                seen = set()
                for record in records:
                    if record["id"] in seen:         # duplicate within one diff
                        skipped += 1
                        continue
                    seen.add(record["id"])
                    if sink.exists(record["id"]):
                        skipped += 1
                        # redelivery after a crash between put and status update
                        if record["source"] == SOURCE_PARTNER:
                            submissions.published(record["id"], None)
                    else:
                        new.append(record)

                untagged = []
                if new:
                    summary = tag_events(prepare_records(new), output_path=TAGGED_PATH)
                    tagged = summary["results"]          # {id: dims}
                    for record in merge(new, tagged):    # full record + id + tags
                        if record["id"] not in tagged:
                            untagged.append(record["id"])
                            continue
                        sink.put(sanitize(record))       # raises on failure
                        written += 1
                        if record["source"] == SOURCE_PARTNER:
                            submissions.published(record["id"], record["tags"])

                if untagged:
                    # Keep the message: tagged records are already written and
                    # will be skipped on redelivery, so only these get re-tagged.
                    raise RuntimeError(f"{len(untagged)} record(s) not tagged: {untagged[:5]}")

                source.delete(handle)                # only after success
                log.info(
                    "Message processed: %d record(s), %d new — deleted from queue",
                    len(records), len(new),
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
