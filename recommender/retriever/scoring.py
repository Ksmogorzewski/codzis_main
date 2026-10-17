"""Soft preferences and variety: small nudges on top of the cosine similarity.

Hard filters (filters.py) decide WHAT may be recommended; this module only reorders it.
It uses the tagger's closed taxonomy (`tags`) and the data facets (`facets`), which a
free-text embedding can miss. Each boost is small, so a strong semantic match still wins.

Recognised user fields (all optional; lists of taxonomy values from tagger/prompt.py):
    themes, formats, occasion, activity_level, setting, registration, accessibility
    time_of_day                  "rano" / "popołudnie" / "wieczór" (as in facets.timeOfDay)
    home_district (str), near_districts (list)   closer events first

`preference_boost()` also returns WHAT matched, so a caller can explain a recommendation
without an LLM.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from ..chunker import event_district

BOOSTS = {
    "themes": 0.08,
    "formats": 0.04,
    "occasion": 0.03,
    "activity_level": 0.03,
    "setting": 0.02,
    "registration": 0.03,
    "accessibility": 0.05,
    "time_of_day": 0.03,
    "home_district": 0.05,
    "near_districts": 0.025,
}
EXTRA_THEME = 0.02  # per additional matching theme
# Month-long "events" are usually programmes or services, not something to do today;
# exhibitions are the exception (open daily for weeks).
LONG_SPAN_DAYS, LONG_SPAN_PENALTY = 7, 0.06
VERY_LONG_SPAN_DAYS, VERY_LONG_SPAN_PENALTY = 120, 0.04

# user field -> tags dimension
TAG_FIELDS = {
    "themes": "theme",
    "formats": "format",
    "occasion": "occasion",
    "activity_level": "activity_level",
    "setting": "setting",
    "registration": "registration",
    "accessibility": "accessibility",
}
BOTH_SETTINGS = "W pomieszczeniu i na zewnątrz"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in ([value] if isinstance(value, str) else value) if v]


def time_of_day(slot: dict | None) -> str | None:
    """Time of day of a slot from filters.next_slot (same buckets as tagger/facets.py).
    None for all-day and multi-day slots (an exhibition's opening hour says nothing)."""
    if not slot or slot.get("allDay") or _multi_day(slot):
        return None
    start = slot.get("start") or ""
    hour = start[11:13] if "T" in start else start[:2]  # ISO datetime or "HH:MM"
    if not hour.isdigit():
        return None
    hour = int(hour)
    return "rano" if hour < 12 else "popołudnie" if hour < 17 else "wieczór"


def _multi_day(slot: dict) -> bool:
    start, end = slot.get("start") or "", slot.get("end") or ""
    return "T" in start and "T" in end and start[:10] != end[:10]


def _span_days(slot: dict | None) -> int:
    """How many days a dated slot lasts (0 for one-day slots and weekly classes)."""
    if not slot or not _multi_day(slot):
        return 0
    try:
        return (date.fromisoformat(slot["end"][:10]) - date.fromisoformat(slot["start"][:10])).days
    except ValueError:
        return 0


def preference_boost(event: dict, user: dict, slot: dict | None = None) -> tuple[float, dict[str, list[str]]]:
    """(score adjustment, matched values per user field). `slot` = the time the user would go."""
    tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
    boost = 0.0
    matched: dict[str, list[str]] = {}

    for field, dim in TAG_FIELDS.items():
        wanted = _as_list(user.get(field))
        if not wanted:
            continue
        values = _as_list(tags.get(dim))
        if dim == "setting" and BOTH_SETTINGS in values:
            values += ["W pomieszczeniu", "Na zewnątrz"]
        hits = [v for v in dict.fromkeys(values) if v in wanted]
        if hits:
            matched[field] = hits
            boost += BOOSTS[field] + (EXTRA_THEME * (len(hits) - 1) if field == "themes" else 0.0)

    wanted_times = _as_list(user.get("time_of_day"))
    if wanted_times and not (slot and _multi_day(slot)):
        slot_time = time_of_day(slot)
        facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
        times = [slot_time] if slot_time else [] if facets.get("multiDay") else _as_list(facets.get("timeOfDay"))
        hits = [t for t in times if t in wanted_times]
        if hits:
            matched["time_of_day"] = hits
            boost += BOOSTS["time_of_day"]

    days = _span_days(slot)
    if days > LONG_SPAN_DAYS and "Wystawa" not in _as_list(tags.get("format")):
        boost -= LONG_SPAN_PENALTY
    if days > VERY_LONG_SPAN_DAYS:
        boost -= VERY_LONG_SPAN_PENALTY

    district = event_district(event)
    if district and district == user.get("home_district"):
        matched["district"] = ["home"]
        boost += BOOSTS["home_district"]
    elif district and district in _as_list(user.get("near_districts")):
        matched["district"] = ["near"]
        boost += BOOSTS["near_districts"]

    return boost, matched


def diversify(candidates: list, top_k: int, venue_penalty: float = 0.06, theme_penalty: float = 0.02) -> list:
    """Greedy top-k (candidates sorted best-first) that spreads results across venues and
    main themes, so one pool or one cinema does not fill the whole list."""
    pool = list(candidates)
    picked: list = []
    venues: Counter = Counter()
    themes: Counter = Counter()

    def adjusted(c) -> float:
        return c.score - venue_penalty * venues[_venue_key(c)] - theme_penalty * themes[_theme_key(c)]

    while pool and len(picked) < top_k:
        best = max(pool, key=adjusted)  # max() keeps the first (better-ranked) on ties
        pool.remove(best)
        picked.append(best)
        venues[_venue_key(best)] += 1
        themes[_theme_key(best)] += 1
    return picked


def _venue_key(c) -> str:
    name = ((c.event.get("venue") or {}).get("name") or "").strip().lower()
    return name or f"id:{c.event_id}"  # unknown venue: no penalty


def _theme_key(c) -> str:
    themes = _as_list((c.event.get("tags") or {}).get("theme"))
    return themes[0] if themes else f"id:{c.event_id}"
