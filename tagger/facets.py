#!/usr/bin/env python3
"""
Facets — search parameters computed from the data itself (no LLM).

Pure, no I/O. Complements the LLM tags with things the data states exactly:
    timeOfDay  ["rano", "popołudnie", "wieczór"]  local start times (offset from the record)
    days       ["monday", ...]                    weekdays of starts / weekly schedule
    weekend    bool
    multiDay   bool                               an occurrence lasting more than a day (e.g. exhibitions)
    recurring  bool                               weekly classes (kind = "recurring")

Plus expires_at(): DynamoDB TTL (epoch seconds) one day after the event ends.
"""

from datetime import datetime, timedelta

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
TTL_GRACE = timedelta(days=1)


def facets(record: dict) -> dict:
    hours, days, multi_day = set(), set(), False

    for o in record.get("occurrences") or []:
        start, end = _parse(o.get("start")), _parse(o.get("end"))
        if not start:
            continue
        days.add(DAYS[start.weekday()])
        if end and end - start > timedelta(days=1):
            multi_day = True
        if not o.get("allDay"):
            hours.add(start.hour)

    for s in record.get("schedule") or []:
        if s.get("day") in DAYS:
            days.add(s["day"])
        if s.get("start"):
            hours.add(int(s["start"][:2]))

    return {
        "timeOfDay": sorted({_time_of_day(h) for h in hours}, key=["rano", "popołudnie", "wieczór"].index),
        "days": [d for d in DAYS if d in days],
        "weekend": bool(days & {"saturday", "sunday"}),
        "multiDay": multi_day,
        "recurring": record.get("kind") == "recurring",
    }


def expires_at(record: dict) -> int | None:
    """TTL for events with an end date; weekly classes (no endsAt) never expire."""
    ends = record.get("endsAt")
    if not ends:
        return None
    return int((datetime.fromisoformat(ends.replace("Z", "+00:00")) + TTL_GRACE).timestamp())


def _time_of_day(hour: int) -> str:
    if hour < 12:
        return "rano"
    if hour < 17:
        return "popołudnie"
    return "wieczór"


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
