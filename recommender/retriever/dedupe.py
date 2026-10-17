"""Collapse recurring events (same title, multiple dates) into one entry.

The raw Warsaw data has one ROW per occurrence, each with a distinct URL and a
single date in `occurrence`. This makes the same event (e.g. a weekly club meeting)
appear many times in results, crowding out diverse options. The same happens in the
target table (e.g. one record per group of a swimming class).

We dedupe by NORMALIZED TITLE, keeping the "best" occurrence. Because each row is a
separate occurrence, "best" = the one the retriever scores highest (passed in), or
the earliest upcoming date as a neutral default. The retriever runs it AFTER the hard
filters, so the kept row is one that fits the user (their district, their dates).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_title(title: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace/punctuation for grouping."""
    t = (title or "").strip().lower()
    # NFKD-decompose then drop combining marks -> removes Polish diacritics.
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    # collapse non-alphanumerics to single spaces so punctuation variants group together
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def dedupe_events(
    events: list[dict],
    score_by_id: dict[str, float] | None = None,
) -> list[dict]:
    """Collapse events sharing a normalized title into one record.

    score_by_id: optional {event_id: relevance_score}. The occurrence with the
    highest score is kept; ties / no scores fall back to the earliest `from` date,
    then first-seen order. Preserves the order of first appearance of each group.
    """
    def sort_key(e: dict):
        # primary: higher score is better -> negate; secondary: earlier date.
        sc = -(score_by_id.get(e.get("id", ""), 0.0) or 0.0) if score_by_id else 0.0
        starts = _starts(e)
        return (sc, min(starts) if starts else "")

    groups: dict[str, list[dict]] = {}
    order: list[str] = []  # preserve first-appearance order of each group
    for e in events:
        key = normalize_title(e.get("title", ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(e)

    deduped: list[dict] = []
    for key in order:
        members = groups[key]
        best = sorted(members, key=sort_key)[0]
        # Attach the group's distinct upcoming dates so the single row still shows
        # when it recurs (does not affect embedding, which uses title+lead).
        all_dates = [start for m in members for start in _starts(m)]
        if all_dates:
            best = dict(best)
            best["all_dates"] = sorted(set(all_dates))
        deduped.append(best)

    return deduped


def _starts(event: dict) -> list[str]:
    """Occurrence start datetimes (ISO): schema v1 `occurrences`, raw API `occurrence`."""
    starts = [str(o["start"]) for o in event.get("occurrences") or [] if isinstance(o, dict) and o.get("start")]
    starts += [str(o["from"]) for o in event.get("occurrence") or [] if isinstance(o, dict) and o.get("from")]
    return starts
