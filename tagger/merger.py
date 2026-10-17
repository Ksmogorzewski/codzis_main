#!/usr/bin/env python3
"""
Merger — join the full API record with the LLM tags into one file.

Reads:
    data/raw_events.json    - full API response
    data/tagged.jsonl       - LLM output (id + theme/audience/format/cost/mode)
Writes:
    data/events_tagged.json - one record per event: full API data + "id" + "tags"

Usage:
    python3 -m tagger.merger
"""

import json
from pathlib import Path

from .config import DATA_DIR, event_id

RAW_PATH = DATA_DIR / "raw_events.json"
TAGGED_PATH = DATA_DIR / "tagged.jsonl"
OUT_PATH = DATA_DIR / "events_tagged.json"


def merge(raw_events: list[dict], tagged: dict) -> list[dict]:
    """Return each full API record with `id` and `tags` added.

    The original API fields are preserved untouched; the LLM dimensions
    (theme, audience, format, cost, mode) are added under the "tags" key.
    """
    merged = []
    for raw in raw_events:
        record = dict(raw)                      # full original API record
        record["id"] = event_id(raw.get("url"))  # stable id
        record["tags"] = tagged.get(record["id"], {})  # LLM tags
        merged.append(record)
    return merged


def load_tagged(path: Path = TAGGED_PATH) -> dict:
    """Read tagged.jsonl into {id: {dimension values}}."""
    tagged = {}
    if not path.exists():
        return tagged
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        eid = obj.pop("id", None)
        if eid:
            tagged[eid] = obj
    return tagged


def main() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    tagged = load_tagged()
    merged = merge(raw, tagged)

    OUT_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tagged_count = sum(1 for m in merged if m.get("tags"))
    print(f"Merged {len(merged)} events -> {OUT_PATH}")
    print(f"Events with tags: {tagged_count}")


if __name__ == "__main__":
    main()
