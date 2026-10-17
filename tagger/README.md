# Model Tagowania — event tagger (ECS one-shot task)

Tags Warsaw city events into categories using DeepSeek (`deepseek-flash`) via the
OpenAI-compatible API, then writes the tagged records to DynamoDB.

Designed to run as a **one-shot ECS container**: it polls an SQS queue for a batch
of raw events (the diff from your backend), tags them, upserts them into a DynamoDB
table (skipping records that already exist), deletes the processed SQS messages, and
exits with code `0` (success) or `1` (failure) — which is how ECS knows the task ended.

## Structure

```
run_task.py              # one-shot ECS entrypoint: SQS -> tag -> DynamoDB -> exit
tagger/                  # the importable tagging module
  __init__.py            # public API: tag_events, merge, prepare_records
  config.py              # paths, .env loader, event_id, strip_html
  prepare.py             # prepare_records(raw_events) — raw API -> slim records
  client.py              # DeepSeekClient (API plumbing)
  chunker.py             # token-budgeted chunking
  prompt.py              # DIMENSIONS (multi-dim taxonomy) + prompt builder
  parser.py              # parse & validate model output
  orchestrator.py        # run loop, token accounting, incremental save
  merger.py              # merge(raw_events, tagged) — full record + tags
  sqs_source.py          # SQSSource — receive/delete SQS messages
  dynamodb_sink.py       # DynamoDBSink — exists/put + DynamoDB sanitize
requirements.txt
.env                     # DEEPSEEK_API_KEY (gitignored); AWS via ECS task-role
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`.env` holds `DEEPSEEK_API_KEY`. AWS credentials are **not** in code — boto3 uses the
ECS task-role IAM role automatically. DevOps configures:

| Env var | Purpose |
|---|---|
| `SQS_QUEUE_URL` | Source queue (backend drops diffs here) |
| `DYNAMODB_TABLE` | Target table (default `warsaw_events` if unset) |
| `AWS_REGION` | Table region (default `eu-central-1`) |

ECS also needs a task-role IAM policy granting SQS (`ReceiveMessage`, `DeleteMessage`)
and DynamoDB (`GetItem`, `PutItem`).

## Run

```bash
python3 run_task.py               # poll SQS until empty, then exit
python3 run_task.py --max-batches 5
```

Exit code `0` = all batches processed; `1` = at least one failure (failed messages are
left on the queue, not deleted).

## Use as a module

```python
from tagger import tag_events, merge, prepare_records

slim = prepare_records(raw_events)     # raw API records -> slim records
summary = tag_events(slim)             # {"results", "usage", "failures"}
merged = merge(raw_events, summary["results"])   # full records + "id" + "tags"
```

## Where to edit

| Change | File |
|---|---|
| Dimensions (taxonomy) | `tagger/prompt.py` → `DIMENSIONS` |
| Model / endpoint | `tagger/client.py` |
| Chunk token budget | `tagger/orchestrator.py` → `TARGET_TOKENS` |
