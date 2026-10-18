#!/usr/bin/env python3
"""
run_task.py — ONE-SHOT ECS task entrypoint.

Control flow:
    1. Receive a batch of messages from SQS (env SQS_QUEUE_URL).
       Each message body is a JSON array of raw event records (a diff).
    2. For each message:
         normalize(raw)       -> schema v1 passes through; legacy raw Warsaw records fixed up
         per record, against the item already in the table (BEFORE any LLM call):
             same contentHash + same tagInputHash  -> skip
             changed, but the model input is the same -> write with the existing tags (no LLM)
             new, or title/description/hints/taxonomy changed -> tag
         tag_events(prepare_records(to_tag))  -> LLM tags (tagger / DeepSeek)
         record + tags + facets (from data) + expiresAt (TTL) + photo in the standard
             (tagger/images.py: WebP 3:2 up to 1200x800 in the photos bucket) -> sink.put(sanitize(record))
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
    PHOTOS_BUCKET, PHOTOS_BASE_URL (optional) photos in the standard; without them imageUrl stays the source
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
from tagger.facets import expires_at, facets
from tagger.images import S3Images, normalize_image
from tagger.normalize import SOURCE_PARTNER, normalize
from tagger.parser import apply_declared
from tagger.prepare import prepare_record, prepare_records, tag_input_hash
from tagger.prompt import taxonomy_version
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
    stats = {"tagged": 0, "reused_tags": 0, "skipped": 0, "failed_messages": 0}
    taxonomy = taxonomy_version()

    source = SQSSource()
    sink = DynamoDBSink()
    submissions = SubmissionStatus()
    images = S3Images.from_env()

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
                stats["failed_messages"] += 1
                continue

            try:
                records = []
                for raw in raw_events:
                    try:
                        records.append(normalize(raw))
                    except ValueError as e:
                        log.error("Dropping invalid record (%s): %.80s", e, raw)

                to_tag, seen = [], set()
                for record in records:
                    if record["id"] in seen:         # duplicate within one diff
                        stats["skipped"] += 1
                        continue
                    seen.add(record["id"])
                    record["tagInputHash"] = tag_input_hash(prepare_record(record), taxonomy)
                    existing = sink.get(record["id"])

                    if existing is None:
                        to_tag.append(record)
                    elif not record.get("contentHash") or (
                        existing.get("contentHash") == record["contentHash"]
                        and existing.get("tagInputHash") == record["tagInputHash"]
                    ):
                        # unchanged (records without contentHash, e.g. partner, are never updated)
                        stats["skipped"] += 1
                        if record["source"] == SOURCE_PARTNER:
                            # redelivery after a crash between put and status update
                            submissions.published(record["id"], None)
                    elif existing.get("tagInputHash") == record["tagInputHash"] and existing.get("tags"):
                        # e.g. a new date: same model input -> keep tags, no LLM call
                        record["tags"] = existing["tags"]
                        write(sink, submissions, record, taxonomy, images)
                        stats["reused_tags"] += 1
                    else:
                        to_tag.append(record)

                untagged = []
                if to_tag:
                    summary = tag_events(prepare_records(to_tag), output_path=TAGGED_PATH)
                    tagged = summary["results"]          # {id: dims}
                    usage = summary["usage"]
                    log.info(
                        "LLM: %d record(s), %d prompt + %d completion tokens, ~$%.4f",
                        len(to_tag), usage["prompt_tokens"], usage["completion_tokens"], usage["approx_cost_usd"],
                    )
                    for record in merge(to_tag, tagged):  # full record + id + tags
                        if record["id"] not in tagged:
                            untagged.append(record["id"])
                            continue
                        write(sink, submissions, record, taxonomy, images)
                        stats["tagged"] += 1

                if untagged:
                    # Keep the message: tagged records are already written and
                    # will be skipped on redelivery, so only these get re-tagged.
                    raise RuntimeError(f"{len(untagged)} record(s) not tagged: {untagged[:5]}")

                source.delete(handle)                # only after success
                log.info("Message processed: %d record(s), %d sent to the model — deleted from queue",
                         len(records), len(to_tag))
            except Exception as e:
                # Do NOT delete the message: SQS visibility timeout will
                # redeliver it (or the DLQ will catch it after max receives).
                log.error("Message failed (kept on queue): %s", e, exc_info=True)
                all_ok = False
                stats["failed_messages"] += 1
    else:
        log.error("Hit --max-batches=%d without draining the queue",
                  args.max_batches)
        all_ok = False

    log.info(
        "Finished: %d tagged, %d updated with existing tags, %d unchanged/skipped, %d failed message(s)",
        stats["tagged"], stats["reused_tags"], stats["skipped"], stats["failed_messages"],
    )
    return 0 if all_ok else 1


def write(sink, submissions, record: dict, taxonomy: str, images: S3Images | None = None) -> None:
    """Declared values over model tags, facets + TTL, photo in the standard, upsert; partner records also
    update the portal status. A photo that fails keeps the source imageUrl (never blocks the write)."""
    record = normalize_image(record, images)
    record["tags"] = apply_declared(record.get("tags"), record.get("declared"))
    record["facets"] = facets(record)
    record["taxonomyVersion"] = taxonomy
    record["expiresAt"] = expires_at(record)
    sink.put(sanitize(record))                   # raises on failure
    if record["source"] == SOURCE_PARTNER:
        submissions.published(record["id"], record["tags"])


if __name__ == "__main__":
    sys.exit(main())
