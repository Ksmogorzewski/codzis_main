"""GET /api/me/events: wydarzenia, na które jestem zapisany (zakładka „Twoje”), na atrapie DynamoDB."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.client_api.conftest import call

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=WARSAW)  # środa

ALA = {"sub": "user-1", "email": "ala@example.com", "name": "Ala"}
BARTEK = {"sub": "user-2", "email": "bartek@example.com", "name": "Bartek"}


def record(event_id, start, end=None, **extra):
    occurrence = {"start": start, "allDay": False}
    if end:
        occurrence["end"] = end
    return {
        "id": event_id,
        "origin": "um_warszawa",
        "source": "um_kalendarz",
        "kind": "event",
        "title": f"Wydarzenie {event_id}",
        "text": "<p>Opis</p>",
        "district": "Wola",
        "occurrences": [occurrence],
        "tags": {"theme": ["Muzyka"]},
    } | extra


YOGA = {
    "id": "yoga",
    "origin": "um_warszawa",
    "source": "um_zajecia",
    "kind": "recurring",
    "title": "Joga w parku",
    "schedule": [{"day": "friday", "start": "18:00", "end": "19:00"}],
}


@pytest.fixture
def api(client_api, monkeypatch, events_table):
    monkeypatch.setattr(client_api.routes.common, "now", lambda: NOW)
    for item in [
        record("today", "2026-10-14T19:00:00+02:00"),
        record("saturday", "2026-10-17T10:00:00+02:00"),
        record("next-week", "2026-10-21T10:00:00+02:00"),
        record("last-week", "2026-10-07T10:00:00+02:00", "2026-10-07T12:00:00+02:00"),
        record("yesterday", "2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"),
        YOGA,
    ]:
        events_table.put_item(Item=item)
    return client_api


def save(api, event_id, claims=ALA):
    return call(api, "PUT /api/events/{id}/save", claims=claims, path={"id": event_id})


def my_events(api, claims=ALA):
    status, body = call(api, "GET /api/me/events", claims=claims)
    assert status == 200
    return body["items"]


def test_empty(api):
    assert call(api, "GET /api/me/events") == (200, {"items": []})


def test_upcoming_by_next_term_then_past_newest_first(api):
    for event_id in ["last-week", "next-week", "yoga", "today", "yesterday", "saturday"]:
        save(api, event_id)

    items = my_events(api)
    assert [(c["id"], c["past"]) for c in items] == [
        ("today", False),
        ("yoga", False),  # piątek 16.10
        ("saturday", False),
        ("next-week", False),
        ("yesterday", True),
        ("last-week", True),
    ]
    assert items[1]["slot"] == {
        "recurring": True,
        "date": "2026-10-16",
        "day": "friday",
        "start": "18:00",
        "end": "19:00",
    }
    # minione: ostatni termin zamiast najbliższego
    assert items[4]["slot"]["start"] == "2026-10-13T10:00:00+02:00"


def test_card_has_counts_saved_and_saved_at(api):
    save(api, "saturday")
    save(api, "saturday", BARTEK)
    [card] = my_events(api)
    assert card["id"] == "saturday"
    assert card["saves"] == 2 and card["saved"] is True
    assert card["savedAt"]
    assert card["title"] == "Wydarzenie saturday"
    assert "text" not in card and "reason" not in card


def test_only_my_saves(api, attendance_table):
    save(api, "today", BARTEK)
    save(api, "saturday")
    # dane testowe na demo (scripts/seed_demo.py) to zapisy innych osób
    attendance_table.put_item(
        Item={"eventId": "next-week", "userId": "seed-1", "savedAt": "2026-10-14T08:00:00Z", "seed": True}
    )
    assert [c["id"] for c in my_events(api)] == ["saturday"]
    assert [c["id"] for c in my_events(api, BARTEK)] == ["today"]


def test_skips_events_missing_from_codzis_events(api, attendance_table):
    save(api, "today")
    # wydarzenie wygasło z codzis-events (TTL), a zapis został do analityki
    attendance_table.put_item(Item={"eventId": "gone", "userId": "user-1", "savedAt": "2026-10-14T09:00:00Z"})
    assert [c["id"] for c in my_events(api)] == ["today"]


def test_after_unsave_disappears(api):
    save(api, "today")
    call(api, "DELETE /api/events/{id}/save", claims=ALA, path={"id": "today"})
    assert my_events(api) == []


def test_capped_at_100_newest_saves(api, events_table, attendance_table):
    for i in range(105):
        event_id = f"e{i:03d}"
        events_table.put_item(Item=record(event_id, f"2026-10-{15 + i % 10}T10:00:00+02:00"))
        attendance_table.put_item(
            Item={"eventId": event_id, "userId": "user-1", "savedAt": f"2026-10-14T09:{i // 60:02d}:{i % 60:02d}Z"}
        )
    items = my_events(api)
    assert len(items) == 100
    # najstarsze zapisy (e000-e004) odpadają
    assert {f"e{i:03d}" for i in range(5)}.isdisjoint(c["id"] for c in items)
