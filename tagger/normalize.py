#!/usr/bin/env python3
"""
Normalize — make records from every source fit one target-table schema.

Records with "schemaVersion" (importer, partner portal) are already standardized
and pass through unchanged. Legacy raw Warsaw-API records get, before tagging:
    - "id"      record's own id (partner UUID) or stable hash of url
    - "source"  "partner" (set by the partner portal) or "um_warszawa" (default)
    - Warsaw API quirks: "+01" offsets -> "+01:00", http:// images -> https://
    - "startsAt"/"endsAt" in UTC, derived from "occurrence" (for sorting/indexes;
      DynamoDB cannot index into the nested occurrence list)
"""

import re
from datetime import datetime, timezone

from .config import record_id

SOURCE_PARTNER = "partner"
SOURCE_UM = "um_warszawa"


def normalize(raw: dict) -> dict:
    """Return a normalized copy. Raises ValueError if the record has no id/url."""
    if not raw.get("id") and not raw.get("url"):
        raise ValueError("record has neither id nor url - cannot derive a stable id")
    if raw.get("schemaVersion"):
        # Already in the target schema (importer / partner portal) - see src/importer/schema.py
        return dict(raw)

    record = dict(raw)
    record["id"] = record_id(raw)
    record.setdefault("source", SOURCE_UM)

    if record["source"] != SOURCE_PARTNER:
        record["occurrence"] = [
            {**o, "from": _iso_offset(o.get("from")), "to": _iso_offset(o.get("to"))}
            for o in raw.get("occurrence") or []
        ]
        record["image"] = _https_image(raw.get("image"))

    starts, ends = [], []
    for o in record.get("occurrence") or []:
        start = _parse(o.get("from"))
        end = _parse(o.get("to")) or start
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    record.setdefault("startsAt", _utc(min(starts)) if starts else None)
    record.setdefault("endsAt", _utc(max(ends)) if ends else None)
    return record


def _iso_offset(value):
    """'2027-01-29T19:00:00+01' (Warsaw API) -> '2027-01-29T19:00:00+01:00'."""
    if not value:
        return value
    return re.sub(r"([+-]\d{2})$", r"\1:00", value)


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _utc(dt):
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _https_image(image):
    # Warsaw API serves images over http://, which browsers block on HTTPS pages
    if not isinstance(image, dict):
        return image
    return {
        size: {**variant, "path": re.sub(r"^http://", "https://", variant.get("path") or "")}
        if isinstance(variant, dict) else variant
        for size, variant in image.items()
    }
