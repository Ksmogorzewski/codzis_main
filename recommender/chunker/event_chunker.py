"""Turn raw event records (DynamoDB / API shape) into embeddable text chunks.

Each event normally yields exactly ONE chunk. A size guard splits pathologically
long events on sentence boundaries so no chunk ever silently exceeds a model limit.

Public API:
    chunk_events(events, max_chars=MAX_CHUNK_CHARS) -> list[EventChunk]
    build_event_text(event) -> str
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .types import EventChunk

# Polish event text is short (measured: full 559-event dataset max lead = 500 chars,
# longest combined title+categories+lead ~ 800 chars). 2000 chars is a safe ceiling
# that no normal event reaches, but it protects against a bad/merged record.
MAX_CHUNK_CHARS = 2000

# Sentence split that keeps Polish punctuation (., !, ?, ;) plus newlines.
_SENTENCE_RE = re.compile(r"(?<=[.!?;。！？；])\s+|\n+")


# --------------------------------------------------------------------------- #
# Field normalisation
# --------------------------------------------------------------------------- #
def _first_name(obj: Any) -> str | None:
    """Extract a display name from the API's list-of-{name} fields.

    `localization` / `address` look like [{"name": "Śródmieście"}] or [].
    Returns the first non-empty name, else None.
    """
    if isinstance(obj, list):
        for entry in obj:
            if isinstance(entry, dict):
                name = (entry.get("name") or "").strip()
                if name:
                    return name
            elif isinstance(entry, str) and entry.strip():
                return entry.strip()
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    return None


def _join_parts(parts: list[str]) -> str:
    """Join text parts with '. ' without doubling terminal punctuation.

    ['Czeski dzień', 'Kultura', 'Poznaj Czechów...'] ->
    'Czeski dzień. Kultura. Poznaj Czechów...'
    """
    out = ""
    for part in parts:
        if not out:
            out = part
        elif out.endswith((".", "!", "?", ";")):
            out = f"{out} {part}"
        else:
            out = f"{out}. {part}"
    return re.sub(r"\s+", " ", out).strip()


def _categories(event: dict) -> list[str]:
    cats: list[str] = []
    for c in event.get("category") or []:
        if isinstance(c, dict):
            name = (c.get("name") or "").strip()
        else:
            name = str(c).strip()
        if name:
            cats.append(name)
    return cats


# --------------------------------------------------------------------------- #
# Text building
# --------------------------------------------------------------------------- #
def build_event_text(event: dict, max_chars: int = MAX_CHUNK_CHARS) -> str:
    """Build the canonical embedding text for one event.

    Format: "Title. Cat1, Cat2. Lead/text..."
    Keeps it to a single chunk; if it would exceed `max_chars`, it is split on
    sentence boundaries and only the first `max_chars` worth is kept (the caller
    uses `chunk_event` when it needs every part).
    """
    title = (event.get("title") or "").strip()
    cats = _categories(event)
    body = (event.get("lead") or event.get("text") or "").strip()

    parts: list[str] = [p.strip() for p in (title, ", ".join(cats), body) if p and p.strip()]
    text = _join_parts(parts)
    if len(text) <= max_chars:
        return text

    # Too long: accumulate sentences up to the budget (reuse the punctuation-safe joiner).
    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    out: list[str] = []
    length = 0
    for s in sentences:
        add = len(s) + (0 if not out else 1 if out[-1].endswith((".", "!", "?", ";")) else 2)
        if out and length + add > max_chars:
            break
        out.append(s)
        length += add
        if not out and length > max_chars:  # single sentence already too long
            return s[:max_chars]
    return _join_parts(out) if out else text[:max_chars]


def _split_sentences(text: str, max_chars: int) -> list[str]:
    """Split `text` into sentence-bounded chunks each <= max_chars."""
    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for s in sentences:
        add = len(s) + (0 if not cur else 1 if cur[-1].endswith((".", "!", "?", ";")) else 2)
        if cur and cur_len + add > max_chars:
            chunks.append(_join_parts(cur))
            cur, cur_len = [s], len(s)
        else:
            cur.append(s)
            cur_len += add
    if cur:
        chunks.append(_join_parts(cur))
    # Hard-split any single sentence that is still too long (no good break point).
    final: list[str] = []
    for c in chunks:
        while len(c) > max_chars:
            final.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            final.append(c)
    return final


# --------------------------------------------------------------------------- #
# Public chunker
# --------------------------------------------------------------------------- #
def chunk_event(event: dict, max_chars: int = MAX_CHUNK_CHARS) -> list[EventChunk]:
    """Chunk a single event into one or more EventChunks."""
    event_id = event.get("id") or ""
    url = event.get("url") or ""
    title = (event.get("title") or "").strip()
    district = _first_name(event.get("localization"))
    cats = _categories(event)

    full = build_event_text(event, max_chars=10**9)  # un-truncated; we split below
    if len(full) <= max_chars:
        return [EventChunk(
            event_id=event_id, event_url=url, text=full,
            title=title, district=district, categories=cats,
            chunk_index=0, total_chunks=1,
        )]

    pieces = _split_sentences(full, max_chars)
    return [
        EventChunk(
            event_id=event_id, event_url=url, text=piece,
            title=title, district=district, categories=cats,
            chunk_index=i, total_chunks=len(pieces),
        )
        for i, piece in enumerate(pieces)
    ]


def chunk_events(
    events: Iterable[dict],
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[EventChunk]:
    """Chunk many events. Normally 1 chunk per event; preserves input order."""
    chunks: list[EventChunk] = []
    for event in events:
        chunks.extend(chunk_event(event, max_chars=max_chars))
    return chunks
