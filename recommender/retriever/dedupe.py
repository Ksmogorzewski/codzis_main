"""Collapse recurring events (same title, multiple dates) into one entry.

The raw Warsaw data has one ROW per occurrence, each with a distinct URL and a
single date in `occurrence`. This makes the same event (e.g. a weekly club meeting)
appear many times in results, crowding out diverse options. The same happens in the
target table (e.g. one record per group of a swimming class).

We dedupe by NORMALIZED TITLE, keeping the "best" occurrence. Because each row is a
separate occurrence, "best" = the one the retriever scores highest (passed in), or
the earliest upcoming date as a neutral default. The retriever runs it AFTER the hard
filters, so the kept row is one that fits the user (their district, their dates).

Title normalisation (`normalize_title`) is deliberately conservative but covers the
variation actually present in the Warsaw data:

  * case / punctuation / whitespace        "Koncert JAZZOWY "  == "koncert jazzowy"
  * diacritics, incl. Polish ł             "Pływanie"          == "Plywanie"
  * HTML entities                          "Koncert &amp; taniec" == "Koncert & taniec"
  * zero-width characters                  "Konc\u200bert"    == "Koncert"
  * plural / inflection variants           "Koncerty jazzowe"  == "Koncert jazzowy"
  * group / round markers                  "... - grupa 1"     == "... - grupa 2"
                                           "... (edycja II)"   == "..."

The last two are heuristic: over-grouping only ever hides a *near-duplicate* title
(its dates are preserved in `all_dates`), so a small amount of merging is preferable
to showing eight rows of the same swimming class.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

# Polish letters that Unicode NFKD does NOT decompose into ASCII + combining mark.
# Without this, "pływania" -> "p ywania" (the ł is dropped, splitting the word).
_LETTER_FOLD = str.maketrans({
    "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss",
})

# Zero-width / BOM: invisible characters that split tokens if left in place.
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")

# "grupa 1", "grupa II", "grupa A", "tura 2", "dzień 3", "edycja II", "runda 1",
# "kolejka 4" — same event split into per-group/per-episode rows. Matches the marker
# plus its value so the whole fragment disappears from the key.
_GROUP_MARKER_RE = re.compile(
    r"\b(?:grupa|grupy|grupie|tura|tury|turze|runda|rundy|rundzie|kolejka|kolejki|"
    r"dzien|dnia|edycja|edycji|sezon|sezonu|etap|etapu)"
    r"[\s\-–—]*(?:[0-9]+|[ivx]+|[a-z])\b"
)

# A bare trailing group number in brackets, e.g. "... (2)" / "... [3]" / "... (nr 2)".
_TRAILING_NUMBER_RE = re.compile(r"[\s\-–—]*[(\[]\s*(?:nr\s*)?[0-9]+\s*[)\]]\s*$")

# "&" is used as shorthand for the Polish "i" (and): "Koncert & taniec" == "Koncert i taniec".
_AMPERSAND_RE = re.compile(r"\s*&\s*")

# Polish inflection endings stripped from the end of a token (longest first) so that
# singular/plural and case variants of the same word collapse together:
#   koncerty/koncertow -> koncert, jazzowe/jazzowy -> jazzow, warsztaty -> warsztat
# Only applied to tokens long enough that the stem stays meaningful (>= 4 chars).
# Nominative singular "-a"/"-o" are intentionally NOT stripped ("kino" vs "kina"
# would otherwise become "kino" vs "kin").
_INFLECTION_ENDINGS = ("owie", "ach", "ami", "owi", "ów", "ie", "om", "y", "e", "i")
_MIN_TOKEN_LEN = 5
_MIN_STEM_LEN = 4

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _fold(text: str) -> str:
    """Unescape HTML, drop zero-width chars, fold Polish letters, strip diacritics."""
    t = html.unescape(str(text or ""))
    t = _ZERO_WIDTH_RE.sub("", t)
    t = _AMPERSAND_RE.sub(" i ", t)
    t = t.translate(_LETTER_FOLD)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def normalize_title(title: str, stem: bool = True) -> str:
    """Lowercase, strip diacritics/entities/group markers, collapse whitespace.

    stem=True (default) also strips Polish inflection endings per token, so
    "Koncerty jazzowe" and "Koncert jazzowy" produce the same key.
    """
    t = _fold(title).lower()
    if not stem:
        # Collapse everything non-alphanumeric to single spaces (punctuation variants).
        return re.sub(r"\s+", " ", _NON_ALNUM_RE.sub(" ", t)).strip()

    # Strip group markers while punctuation is still present: the bracket form
    # ("... (2)") needs its brackets, which the alnum collapse below would remove.
    t = _GROUP_MARKER_RE.sub(" ", t)
    t = _TRAILING_NUMBER_RE.sub(" ", t)
    # Collapse everything non-alphanumeric to single spaces (punctuation variants).
    t = re.sub(r"\s+", " ", _NON_ALNUM_RE.sub(" ", t)).strip()
    tokens = []
    for tok in t.split():
        if len(tok) >= _MIN_TOKEN_LEN:
            for end in _INFLECTION_ENDINGS:
                if tok.endswith(end) and len(tok) - len(end) >= _MIN_STEM_LEN:
                    tok = tok[: -len(end)]
                    break
        tokens.append(tok)
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def dedupe_events(
    events: list[dict],
    score_by_id: dict[str, float] | None = None,
) -> list[dict]:
    """Collapse events sharing a normalized title into one record.

    score_by_id: optional {event_id: relevance_score}. The occurrence with the
    highest score is kept; ties / no scores fall back to the earliest `from` date,
    then first-seen order. Preserves the order of first appearance of each group.

    Events whose title normalizes to an empty key (emoji-only, punctuation-only) are
    never grouped together — each is treated as unique.
    """
    def sort_key(e: dict):
        # primary: higher score is better -> negate; secondary: earlier date.
        sc = -(score_by_id.get(e.get("id", ""), 0.0) or 0.0) if score_by_id else 0.0
        starts = _starts(e)
        return (sc, min(starts) if starts else "")

    groups: dict[str, list[dict]] = {}
    order: list[str] = []  # preserve first-appearance order of each group
    for i, e in enumerate(events):
        key = normalize_title(e.get("title", ""))
        if not key:  # un-normalizable title: keep its own group
            key = f"\x00unique:{i}"
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
