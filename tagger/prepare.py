#!/usr/bin/env python3
"""
Prepare — map records to slim model records.

Pure, no I/O: the same transformation is used by the local dev path
(scripts/prepare_data.py) and the ECS one-shot task (run_task.py),
regardless of where the records came from (importer, partner portal, file).

Input: schema v1 records (src/importer/schema.py) or legacy raw Warsaw API records.

Slim model record (empty hints are omitted to save tokens):
    id             - record's own id, else stable hash of url (mapping key)
    title          - event title
    lead           - short summary (may be null)
    description    - full text, HTML stripped, whitespace normalized, truncated
    categories     - existing tags (names only)
    audience_hint  - groups the organiser targets (e.g. "Seniorzy")
    kind           - "event" | "recurring"
    online         - true for online events
    venue          - venue name
"""

import hashlib
import json

from .config import record_id, strip_html

# Long descriptions cost tokens and add noise; the beginning carries the signal.
MAX_DESCRIPTION_CHARS = 1500


def prepare_records(raw_events: list[dict]) -> list[dict]:
    """Map records to slim model records. Pure, no I/O."""
    return [prepare_record(e) for e in raw_events]


def prepare_record(e: dict) -> dict:
    venue = (e.get("venue") or {}).get("name")
    if not venue and e.get("address"):  # legacy raw Warsaw API shape
        venue = (e["address"][0] or {}).get("name")
    slim = {
        "id": record_id(e),
        "title": e.get("title"),
        "lead": e.get("lead"),
        "description": _truncate(strip_html(e.get("text") or ""), MAX_DESCRIPTION_CHARS),
        "categories": [c.get("name") for c in e.get("category") or [] if c.get("name")],
        "audience_hint": e.get("audience") or [],
        "kind": e.get("kind"),
        "online": e.get("online") or None,
        "venue": venue,
    }
    required = {"id", "title", "lead", "description", "categories"}
    return {k: v for k, v in slim.items() if k in required or v not in (None, "", [])}


def tag_input_hash(slim: dict, taxonomy_version: str) -> str:
    """Hash of everything the model sees for this record (+ taxonomy).

    Same hash = the model would get identical input, so existing tags can be reused.
    """
    payload = {k: v for k, v in slim.items() if k != "id"}
    payload["_taxonomy"] = taxonomy_version
    return hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " …"
