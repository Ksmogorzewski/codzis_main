#!/usr/bin/env python3
"""
Prepare — map raw API records to slim model records.

Pure, no I/O: the same transformation is used by the local dev path
(scripts/prepare_data.py) and the ECS one-shot task (run_task.py),
regardless of where the raw records came from (Warsaw API, SQS, file).

Raw record schema (Warsaw API):
    url, title, lead, text, category, localization, address, map,
    occurrence, image, language, availableLanguages

Slim model record:
    id           - record's own id, else stable hash of url (mapping key)
    title        - event title
    lead         - short summary (may be null)
    description  - full text with HTML stripped + whitespace normalized
    categories   - existing tags (names only)
"""

from .config import record_id, strip_html


def prepare_records(raw_events: list[dict]) -> list[dict]:
    """Map raw API records to slim model records. Pure, no I/O."""
    return [
        {
            "id": record_id(e),
            "title": e.get("title"),
            "lead": e.get("lead"),
            "description": strip_html(e.get("text") or ""),
            "categories": [c.get("name") for c in e.get("category") or []],
        }
        for e in raw_events
    ]
