"""Structured hard filters for events (district / cost / mode / audience / price / date).

These are applied as a strict AND pre-filter BEFORE vector ranking: an event must
satisfy every provided filter to be considered. They are NOT embedded.

Events use the target-table schema v1 (src/importer/schema.py): `district`, dated
`occurrences` [{start, end, allDay}] or a weekly `schedule` [{day, start, end}] for
recurring classes (kind="recurring"), and the tagger's `tags` (cost/mode single values,
audience a list). The raw Warsaw API shape (`localization`, `occurrence` [{from, to}])
is still understood.

Cost / mode / audience come from the `tags` dict; when a tag is absent the event is not
excluded by that filter. Every filter accepts a single value or a list (any-of).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..chunker import event_district

WARSAW = ZoneInfo("Europe/Warsaw")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

FAMILY = "Rodziny / wszystkie grupy"
# Groups that are also welcome at events for another group (seniors at events for adults).
AUDIENCE_ALSO = {"Seniorzy (65+)": {"Dorośli (18-64)"}}

# An occurrence without an end is treated as lasting this long.
DEFAULT_DURATION = timedelta(hours=2)
# A weekly class that started this long ago still counts as available today.
LATE_ARRIVAL = timedelta(minutes=30)
# Weekly classes are looked up at most this far ahead.
MAX_WINDOW_DAYS = 31


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


def _parse_datetime(value: Any) -> datetime | None:
    """ISO datetime -> aware datetime (values without an offset are Warsaw time)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time())
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=WARSAW)


def _as_set(value: Any) -> set[str]:
    """A filter value: one string or a list of strings -> set (empty = no constraint)."""
    if value is None:
        return set()
    values = [value] if isinstance(value, str) else value
    return {str(v).strip() for v in values if v is not None and str(v).strip()}


def _event_tags(event: dict) -> dict:
    tags = event.get("tags")
    return tags if isinstance(tags, dict) else {}


def event_price(event: dict) -> float | None:
    """Lowest declared ticket price in PLN (partner events: attributes.price {min, max}), if known."""
    price = (event.get("attributes") or {}).get("price")
    if isinstance(price, dict):
        price = price.get("min") if price.get("min") is not None else price.get("max")
    try:
        return float(price) if price is not None and price != "" else None
    except (TypeError, ValueError):
        return None


def audience_matches(event_audience: Any, wanted: Any) -> bool:
    """The event's audience overlaps the user's groups (family / untagged events always do)."""
    groups = _as_set(event_audience)
    wanted = _as_set(wanted)
    if not groups or not wanted or FAMILY in groups:
        return True
    accepted = set(wanted)
    for group in wanted:
        accepted |= AUDIENCE_ALSO.get(group, set())
    return bool(groups & accepted)


def event_occurrences(event: dict) -> list[tuple[datetime, datetime | None, bool]]:
    """(start, end, all_day) of every dated occurrence, sorted by start."""
    out: list[tuple[datetime, datetime | None, bool]] = []
    for occ in event.get("occurrences") or []:
        if isinstance(occ, dict) and (start := _parse_datetime(occ.get("start"))):
            out.append((start, _parse_datetime(occ.get("end")), bool(occ.get("allDay"))))
    if not out:  # raw Warsaw API shape
        for occ in event.get("occurrence") or []:
            if isinstance(occ, dict) and (start := _parse_datetime(occ.get("from"))):
                out.append((start, _parse_datetime(occ.get("to")), False))
    return sorted(out, key=lambda o: o[0])


def event_date_range(event: dict) -> tuple[date | None, date | None]:
    """Return (start_date, end_date) across all occurrences (min start, max end), Warsaw dates."""
    occurrences = event_occurrences(event)
    if not occurrences:
        return None, None
    start = occurrences[0][0].astimezone(WARSAW).date()
    end = max((e or s) for s, e, _ in occurrences).astimezone(WARSAW).date()
    return start, end


def _is_recurring(event: dict) -> bool:
    return event.get("kind") == "recurring" or (bool(event.get("schedule")) and not event_occurrences(event))


def next_slot(event: dict, date_from: Any = None, date_to: Any = None, now: Any = None) -> dict | None:
    """First time the event can be attended in [date_from, date_to] (Warsaw dates, inclusive)
    that is not over at `now`; None when there is none.

    Dated events  -> {"start", "end", "allDay"} (ISO, as in the occurrence)
    Weekly classes -> {"recurring": True, "date", "day", "start", "end"} ("HH:MM"; date/day are
                      None when the class has no schedule)
    """
    from_d, to_d, now_dt = _parse_date(date_from), _parse_date(date_to), _parse_datetime(now)
    if _is_recurring(event):
        return _schedule_slot(event, from_d, to_d, now_dt)

    for start, end, all_day in event_occurrences(event):
        local_start = start.astimezone(WARSAW)
        if end:
            finish = end
        elif all_day:
            finish = datetime.combine(local_start.date(), time.max, tzinfo=WARSAW)
        else:
            finish = start + DEFAULT_DURATION
        if now_dt and finish < now_dt:
            continue
        if from_d and finish.astimezone(WARSAW).date() < from_d:
            continue
        if to_d and local_start.date() > to_d:
            break  # sorted by start: the rest is even later
        return {"start": start.isoformat(), "end": end.isoformat() if end else None, "allDay": all_day}
    return None


def _schedule_slot(event: dict, from_d: date | None, to_d: date | None, now_dt: datetime | None) -> dict | None:
    slots = [s for s in event.get("schedule") or [] if isinstance(s, dict) and s.get("day") in DAYS]
    if not slots:
        # Ongoing class without a timetable: available, but we cannot say when.
        return {"recurring": True, "date": None, "day": None, "start": None, "end": None}

    now_local = (now_dt or datetime.now(WARSAW)).astimezone(WARSAW)
    first = max(from_d or now_local.date(), now_local.date()) if now_dt else (from_d or now_local.date())
    last = min(to_d or first + timedelta(days=6), first + timedelta(days=MAX_WINDOW_DAYS))
    slots.sort(key=lambda s: s.get("start") or "")

    day = first
    while day <= last:
        for slot in slots:
            if slot["day"] != DAYS[day.weekday()]:
                continue
            if now_dt and day == now_local.date() and slot.get("start"):
                try:
                    begins = datetime.combine(day, time.fromisoformat(slot["start"]), tzinfo=WARSAW)
                except ValueError:
                    begins = None
                if begins and begins + LATE_ARRIVAL < now_dt:
                    continue
            return {"recurring": True, "date": day.isoformat(), "day": slot["day"],
                    "start": slot.get("start"), "end": slot.get("end")}
        day += timedelta(days=1)
    return None


def _is_online(event: dict, tags: dict) -> bool:
    return event.get("online") is True or tags.get("mode") == "Online"


def make_event_filter(user: dict):
    """Build a predicate event -> bool from the structured fields of a UserContext.

    Recognised user fields (each optional; a string or a list of any-of values):
        district          the event's district (online events pass)
        cost, mode        tags.cost / tags.mode
        audience          must overlap tags.audience (see audience_matches)
        max_price         a known price (attributes.price) must not exceed it
        date_from/date_to the event takes place in this window (Warsaw dates)
        now               ISO datetime: drops what is already over (also without a window)
    Missing/None fields impose no constraint.
    """
    want_districts = {d.lower() for d in _as_set(user.get("district"))}
    want_cost = _as_set(user.get("cost"))
    want_mode = _as_set(user.get("mode"))
    want_audience = _as_set(user.get("audience"))
    max_price = user.get("max_price")
    from_d = _parse_date(user.get("date_from"))
    to_d = _parse_date(user.get("date_to"))
    now = user.get("now")

    def predicate(event: dict) -> bool:
        tags = _event_tags(event)
        if want_districts and not _is_online(event, tags):
            if (event_district(event) or "").lower() not in want_districts:
                return False

        if want_cost:
            cost = str(tags.get("cost") or "").strip()
            if cost and cost not in want_cost:
                return False
        if want_mode:
            mode = str(tags.get("mode") or "").strip()
            if mode and mode not in want_mode:
                return False
        if want_audience and not audience_matches(tags.get("audience"), want_audience):
            return False

        if max_price is not None:
            price = event_price(event)
            if price is not None and price > float(max_price):
                return False

        if (from_d or to_d or now) and next_slot(event, from_d, to_d, now) is None:
            return False
        return True

    return predicate
