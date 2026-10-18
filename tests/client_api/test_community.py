"""Eksploruj, zapisy, lista zapisanych i Popularne (handler API klienta) na atrapie DynamoDB."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tests.client_api.conftest import call

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=WARSAW)  # środa; najbliższy tydzień 14-20.10

ALA = {"sub": "user-1", "email": "ala@example.com", "name": "Ala"}
BARTEK = {"sub": "user-2", "email": "bartek@example.com", "name": "Bartek"}
NONAME = {"sub": "user-3", "email": "anon@example.com"}


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
        "text": "<p>Opis <b>wydarzenia</b></p>",
        "district": "Wola",
        "occurrences": [occurrence],
        "tags": {"theme": ["Muzyka"], "cost": "Bezpłatne"},
        "importedAt": "2026-10-14T03:00:00Z",
    } | extra


@pytest.fixture
def api(client_api, monkeypatch, events_table):
    monkeypatch.setattr(client_api, "_now", lambda: NOW)
    for item in [
        record("today", "2026-10-14T19:00:00+02:00"),
        record("tomorrow", "2026-10-15T18:00:00+02:00", district="Mokotów"),
        record("saturday", "2026-10-17T10:00:00+02:00", tags={"theme": ["Sport"], "cost": "Płatne"}),
        record("past", "2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"),
        record("next-week", "2026-10-21T10:00:00+02:00"),
    ]:
        events_table.put_item(Item=item)
    return client_api


def save(api, event_id, claims=ALA):
    return call(api, "PUT /api/events/{id}/save", claims=claims, path={"id": event_id})


def unsave(api, event_id, claims=ALA):
    return call(api, "DELETE /api/events/{id}/save", claims=claims, path={"id": event_id})


# --- GET /api/events ---


def test_explore_today(api):
    status, body = call(api, "GET /api/events")
    assert status == 200
    assert body["when"] == "today"
    assert body["window"] == {"from": "2026-10-14", "to": "2026-10-14"}
    assert body["total"] == 1
    [card] = body["items"]
    assert card["id"] == "today"
    assert card["slot"]["start"] == "2026-10-14T19:00:00+02:00"
    assert card["saves"] == 0 and card["saved"] is False
    assert "text" not in card and "reason" not in card


def test_explore_filters_and_counts(api):
    save(api, "saturday", BARTEK)
    save(api, "saturday", ALA)
    status, body = call(api, "GET /api/events", query={"when": "weekend", "cat": "sport"})
    assert status == 200
    assert body["window"] == {"from": "2026-10-17", "to": "2026-10-18"}
    assert [(c["id"], c["saves"], c["saved"]) for c in body["items"]] == [("saturday", 2, True)]

    _, body = call(api, "GET /api/events", query={"when": "date", "date": "2026-10-15", "district": "Mokotów"})
    assert [c["id"] for c in body["items"]] == ["tomorrow"]


def test_explore_limit(api):
    _, body = call(api, "GET /api/events", query={"when": "date", "date": "2026-10-21", "limit": "1"})
    assert body["total"] == 1 and len(body["items"]) == 1


def test_explore_bad_params(api):
    status, body = call(api, "GET /api/events", query={"when": "kiedyś", "cat": "x"})
    assert status == 400
    assert body["fields"] == ["when", "cat"]
    status, body = call(api, "GET /api/events", query={"when": "date", "date": "2026-13-01"})
    assert status == 400
    assert body["fields"] == ["date"]


def test_explore_uses_cache_for_five_minutes(api, events_table, monkeypatch):
    call(api, "GET /api/events")
    events_table.put_item(Item=record("new", "2026-10-14T20:00:00+02:00"))
    _, body = call(api, "GET /api/events")
    assert [c["id"] for c in body["items"]] == ["today"]  # z pamięci

    clock = api.store._events_cache.clock() + 301
    monkeypatch.setattr(api.store._events_cache, "clock", lambda: clock)
    _, body = call(api, "GET /api/events")
    assert [c["id"] for c in body["items"]] == ["today", "new"]


# --- GET /api/events/{id} ---


def test_event_detail(api):
    save(api, "tomorrow", BARTEK)
    status, body = call(api, "GET /api/events/{id}", path={"id": "tomorrow"})
    assert status == 200
    assert body["id"] == "tomorrow"
    assert body["text"] == "Opis wydarzenia"
    assert body["occurrences"] == [{"start": "2026-10-15T18:00:00+02:00", "allDay": False}]
    assert body["importedAt"] == "2026-10-14T03:00:00Z"
    assert body["slot"]["start"] == "2026-10-15T18:00:00+02:00"
    assert body["schedule"] == []
    assert body["saves"] == 1 and body["saved"] is False


def test_event_detail_404(api):
    status, body = call(api, "GET /api/events/{id}", path={"id": "nie-ma"})
    assert status == 404
    assert body == {"error": "Nie znaleziono wydarzenia"}


# --- PUT/DELETE /api/events/{id}/save ---


def test_save_and_unsave_are_idempotent(api, attendance_table, stats_table):
    assert save(api, "today") == (200, {"saved": True, "saves": 1})
    assert save(api, "today") == (200, {"saved": True, "saves": 1})  # powtórka bez zmian
    assert save(api, "today", BARTEK) == (200, {"saved": True, "saves": 2})

    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-1"})["Item"]
    assert item["name"] == "Ala" and item["savedAt"]
    assert "email" not in item
    stats = stats_table.get_item(Key={"eventId": "today"})["Item"]
    assert stats == {"eventId": "today", "saves": Decimal(2), "kind": "event"}

    assert unsave(api, "today") == (200, {"saved": False, "saves": 1})
    assert unsave(api, "today") == (200, {"saved": False, "saves": 1})
    assert "Item" not in attendance_table.get_item(Key={"eventId": "today", "userId": "user-1"})
    assert unsave(api, "today", BARTEK) == (200, {"saved": False, "saves": 0})


def test_save_without_name_stores_no_name(api, attendance_table):
    save(api, "today", NONAME)
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-3"})["Item"]
    assert "name" not in item


def test_save_without_name_claim_uses_display_name(api, attendance_table, users_table):
    # token bez claimu "name" (np. stara sesja), ale GET /api/me zapisał już imię w users
    users_table.put_item(Item={"userId": "user-3", "email": "anon@example.com", "displayName": "  Cezary  "})
    save(api, "today", NONAME)
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-3"})["Item"]
    assert item["name"] == "Cezary"


def test_save_never_falls_back_to_email(api, attendance_table, users_table):
    users_table.put_item(Item={"userId": "user-3", "email": "anon@example.com"})
    save(api, "today", NONAME)
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-3"})["Item"]
    assert "name" not in item
    _, body = call(api, "GET /api/events/{id}/attendees", claims=NONAME, path={"id": "today"})
    assert body["people"] == [{"userId": "user-3", "name": "Ktoś", "isMe": True, "isFriend": False}]


@pytest.mark.parametrize(
    ("family_name", "expected"),
    [("Kowalska", "Ola K."), ("  łukasiewicz ", "Ola Ł."), ("   ", "Ola"), (None, "Ola")],
)
def test_save_shows_surname_initial_only(api, attendance_table, family_name, expected):
    claims = {"sub": "user-9", "email": "ola@example.com", "name": "Ola", "family_name": family_name}
    save(api, "today", claims)
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-9"})["Item"]
    assert item["name"] == expected
    _, body = call(api, "GET /api/events/{id}/attendees", claims=BARTEK, path={"id": "today"})
    assert body["people"][0]["name"] == expected
    assert "owalska" not in str(body) and "ukasiewicz" not in str(body)


def test_save_without_name_claim_uses_stored_surname_initial(api, attendance_table, users_table):
    users_table.put_item(Item={"userId": "user-3", "displayName": "Cezary", "familyName": "Nowak"})
    save(api, "today", NONAME)
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-3"})["Item"]
    assert item["name"] == "Cezary N."


def test_save_name_claim_wins_over_display_name(api, attendance_table, users_table):
    users_table.put_item(Item={"userId": "user-1", "displayName": "Stare"})
    save(api, "today")
    item = attendance_table.get_item(Key={"eventId": "today", "userId": "user-1"})["Item"]
    assert item["name"] == "Ala"


def test_attendees_read_is_consistent(api, monkeypatch):
    # lista zaraz po zapisie (front odświeża ją od razu) musi już zawierać własny wpis
    calls = []
    client = api.store.attendance_table.meta.client
    original = client.query

    def spy(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(client, "query", spy)
    save(api, "today")
    _, body = call(api, "GET /api/events/{id}/attendees", claims=ALA, path={"id": "today"})
    assert body["people"] == [{"userId": "user-1", "name": "Ala", "isMe": True, "isFriend": False}]
    assert calls and all(c.get("ConsistentRead") is True for c in calls if "IndexName" not in c)


def test_save_unknown_event_404(api, stats_table):
    status, body = save(api, "nie-ma")
    assert status == 404
    assert "Item" not in stats_table.get_item(Key={"eventId": "nie-ma"})


def test_unsave_never_saved_is_noop(api):
    assert unsave(api, "today") == (200, {"saved": False, "saves": 0})


# --- GET /api/events/{id}/attendees ---


def test_attendees_newest_first_without_emails(api, attendance_table):
    save(api, "today", ALA)
    save(api, "today", NONAME)
    attendance_table.update_item(
        Key={"eventId": "today", "userId": "user-1"},
        UpdateExpression="SET savedAt = :t",
        ExpressionAttributeValues={":t": "2026-10-01T00:00:00+00:00"},
    )
    status, body = call(api, "GET /api/events/{id}/attendees", claims=BARTEK, path={"id": "today"})
    assert status == 200
    assert body == {
        "saves": 2,
        "saved": False,
        "people": [
            {"userId": "user-3", "name": "Ktoś", "isMe": False, "isFriend": False},
            {"userId": "user-1", "name": "Ala", "isMe": False, "isFriend": False},
        ],
    }
    # własny wpis zawsze na górze
    _, body = call(api, "GET /api/events/{id}/attendees", claims=ALA, path={"id": "today"})
    assert [p["name"] for p in body["people"]] == ["Ala", "Ktoś"]
    assert "example.com" not in str(body)


def test_attendees_empty(api):
    _, body = call(api, "GET /api/events/{id}/attendees", claims=BARTEK, path={"id": "today"})
    assert body == {"saves": 0, "saved": False, "people": []}


def test_attendees_capped_at_100(api, attendance_table):
    with attendance_table.batch_writer() as batch:
        for n in range(105):
            batch.put_item(
                Item={
                    "eventId": "today",
                    "userId": f"seed-{n}",
                    "name": f"Osoba {n}",
                    "savedAt": f"2026-10-14T10:{n:03d}",
                }
            )
    _, body = call(api, "GET /api/events/{id}/attendees", path={"id": "today"})
    assert len(body["people"]) == 100
    assert body["people"][0]["name"] == "Osoba 104"


# --- GET /api/events/stats ---


def test_stats_for_cards(api):
    save(api, "today", ALA)
    save(api, "today", BARTEK)
    save(api, "tomorrow", BARTEK)
    status, body = call(api, "GET /api/events/stats", claims=ALA, query={"ids": "today,tomorrow,nie-ma"})
    assert status == 200
    assert body == {
        "today": {"saves": 2, "saved": True},
        "tomorrow": {"saves": 1, "saved": False},
        "nie-ma": {"saves": 0, "saved": False},
    }


def test_stats_requires_ids(api):
    status, body = call(api, "GET /api/events/stats", query={})
    assert status == 400 and body["fields"] == ["ids"]
    status, body = call(api, "GET /api/events/stats", query={"ids": ",".join(f"e{n}" for n in range(101))})
    assert status == 400 and body["fields"] == ["ids"]


# --- GET /api/popular ---


def test_popular_next_seven_days_by_saves(api, stats_table):
    for who in (ALA, BARTEK, NONAME):
        save(api, "saturday", who)
    save(api, "today", ALA)
    save(api, "next-week", ALA)  # poza oknem (dziś + 6 dni)
    save(api, "past", BARTEK)  # już się odbyło
    save(api, "tomorrow", BARTEK)
    unsave(api, "tomorrow", BARTEK)  # 0 zapisów - pomijamy
    # zapis na wydarzenie, które wygasło z codzis-events (zapisy zostają do analityki)
    stats_table.put_item(Item={"eventId": "gone", "kind": "event", "saves": 10})

    status, body = call(api, "GET /api/popular", claims=BARTEK)
    assert status == 200
    assert body["window"] == {"from": "2026-10-14", "to": "2026-10-20"}
    assert [(c["id"], c["saves"], c["saved"]) for c in body["items"]] == [("saturday", 3, True), ("today", 1, False)]


def test_popular_empty(api):
    assert call(api, "GET /api/popular") == (200, {"window": {"from": "2026-10-14", "to": "2026-10-20"}, "items": []})
