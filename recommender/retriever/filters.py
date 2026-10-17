"""Structured hard filters for events (district / cost / mode / date).

These are applied as a strict AND pre-filter BEFORE vector ranking: an event must
satisfy every provided filter to be considered. They are NOT embedded.

Cost and mode come from the DynamoDB `tags` dict when present; if absent the event
is treated as "unknown" and only excluded when the filter demands a specific value.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_date(value: Any) -> date | None:
    """Leniently parse ISO datetimes / dates -> date. Returns None if unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Trailing 'Z' / offset variations: cut to the date part as a last resort.
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _event_tags(event: dict) -> dict:
    tags = event.get("tags")
    return tags if isinstance(tags, dict) else {}


def event_date_range(event: dict) -> tuple[date | None, date | None]:
    """Return (start_date, end_date) across all occurrences (min start, max end)."""
    starts: list[date] = []
    ends: list[date] = []
    for occ in event.get("occurrence") or []:
        if not isinstance(occ, dict):
            continue
        s = _parse_date(occ.get("from"))
        e = _parse_date(occ.get("to"))
        if s:
            starts.append(s)
        if e:
            ends.append(e)
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if start and not end:
        end = start
    return start, end


def _overlap(a_start: date | None, a_end: date | None,
             b_start: date | None, b_end: date | None) -> bool:
    """Two date ranges overlap (inclusive). None on either side = no constraint."""
    if a_start is None or b_start is None:
        return True
    a_end = a_end or a_start
    b_end = b_end or b_start
    return a_start <= b_end and b_start <= a_end


def make_event_filter(user: dict):
    """Build a predicate event -> bool from the structured fields of a UserContext.

    Recognised user fields: district, cost, mode, date_from, date_to, audience.
    Missing/None fields impose no constraint.
    """
    want_district = (user.get("district") or "").strip() or None
    want_cost = (user.get("cost") or "").strip() or None
    want_mode = (user.get("mode") or "").strip() or None
    want_audience = (user.get("audience") or "").strip() or None
    from_d = _parse_date(user.get("date_from"))
    to_d = _parse_date(user.get("date_to"))

    def predicate(event: dict) -> bool:
        if want_district:
            locs = event.get("localization") or []
            names = {
                (x.get("name") or "").strip().lower()
                for x in locs
                if isinstance(x, dict)
            }
            if want_district.strip().lower() not in names:
                return False

        tags = _event_tags(event)
        if want_cost:
            cost = (tags.get("cost") or "").strip()
            if cost and cost != want_cost:
                return False
        if want_mode:
            mode = (tags.get("mode") or "").strip()
            if mode and mode != want_mode:
                return False
        if want_audience:
            aud = (tags.get("audience") or "").strip()
            if aud and aud != want_audience:
                return False

        if from_d or to_d:
            s, e = event_date_range(event)
            if s is None:  # no date info -> cannot confirm overlap
                return False
            if not _overlap(s, e, from_d, to_d):
                return False

        return True

    return predicate
