"""Trasy znajomych w handlerze API klienta: kontrakt HTTP, imię wymagane, „Znajomi idą”, „Kto się wybiera”."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.client_api.conftest import call

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=WARSAW)  # środa

ALA = {"sub": "user-1", "email": "ala@example.com", "name": "Ala"}
OLA = {"sub": "user-2", "email": "ola@example.com", "name": "Ola"}
KUBA = {"sub": "user-3", "email": "kuba@example.com", "name": "Kuba"}
BARTEK = {"sub": "user-4", "email": "bartek@example.com", "name": "Bartek"}
ZOSIA = {"sub": "user-5", "email": "zosia@example.com", "name": "Zosia"}
NONAME = {"sub": "user-6", "email": "anon@example.com"}


def record(event_id, start, end=None):
    occurrence = {"start": start, "allDay": False}
    if end:
        occurrence["end"] = end
    return {
        "id": event_id,
        "origin": "um_warszawa",
        "source": "um_kalendarz",
        "kind": "event",
        "title": f"Wydarzenie {event_id}",
        "district": "Wola",
        "occurrences": [occurrence],
        "tags": {"theme": ["Muzyka"]},
    }


@pytest.fixture
def api(client_api, monkeypatch, events_table):
    monkeypatch.setattr(client_api, "_now", lambda: NOW)
    for item in [
        record("e1", "2026-10-15T18:00:00+02:00"),
        record("saturday", "2026-10-17T10:00:00+02:00"),
        record("yesterday", "2026-10-13T10:00:00+02:00", "2026-10-13T12:00:00+02:00"),
        record("no-schedule", None) | {"kind": "recurring", "occurrences": [], "schedule": []},
    ]:
        events_table.put_item(Item=item)
    return client_api


def code_of(api, claims):
    status, body = call(api, "GET /api/friends", claims=claims)
    assert status == 200
    return body["code"]


def invite(api, claims, code):
    return call(api, "POST /api/friends/invite", body={"code": code}, claims=claims)


def befriend(api, a, b):
    invite(api, a, code_of(api, b))
    assert call(api, "PUT /api/friends/requests/{userId}", claims=b, path={"userId": a["sub"]}) == (
        200,
        {"status": "friends"},
    )


def save(api, event_id, claims):
    status, _ = call(api, "PUT /api/events/{id}/save", claims=claims, path={"id": event_id})
    assert status == 200


def going(api, claims=ALA):
    status, body = call(api, "GET /api/friends/going", claims=claims)
    assert status == 200
    return body


def test_routes_require_name(api, users_table):
    requests = [
        ("GET /api/friends", None, None),
        ("POST /api/friends/code", None, None),
        ("POST /api/friends/invite", {"code": "WAW-222222"}, None),
        ("PUT /api/friends/requests/{userId}", None, {"userId": "user-1"}),
    ]
    for route, body, path in requests:
        status, error = call(api, route, body=body, claims=NONAME, path=path)
        assert (status, error["code"]) == (409, "name_required"), route

    # imię zapisane wcześniej (displayName w users) wystarcza
    users_table.put_item(Item={"userId": NONAME["sub"], "displayName": "Zosia"})
    assert call(api, "GET /api/friends", claims=NONAME)[0] == 200


def test_friends_contract(api):
    code = code_of(api, ALA)
    assert call(api, "GET /api/friends", claims=ALA) == (
        200,
        {"code": code, "friends": [], "incoming": [], "outgoing": []},
    )
    assert call(api, "GET /api/friends/code/{code}", claims=OLA, path={"code": code.lower()}) == (
        200,
        {"userId": "user-1", "name": "Ala"},
    )
    assert invite(api, OLA, code) == (200, {"status": "pending", "userId": "user-1", "name": "Ala"})

    _, body = call(api, "GET /api/friends", claims=ALA)
    assert [(r["userId"], r["name"]) for r in body["incoming"]] == [("user-2", "Ola")]
    assert set(body["incoming"][0]) == {"userId", "name", "createdAt"}

    assert call(api, "PUT /api/friends/requests/{userId}", claims=ALA, path={"userId": "user-2"}) == (
        200,
        {"status": "friends"},
    )
    _, body = call(api, "GET /api/friends", claims=OLA)
    assert [(f["userId"], f["name"]) for f in body["friends"]] == [("user-1", "Ala")]
    assert set(body["friends"][0]) == {"userId", "name", "since"}

    assert call(api, "DELETE /api/friends/{userId}", claims=OLA, path={"userId": "user-1"}) == (200, {})
    assert call(api, "GET /api/friends", claims=ALA)[1]["friends"] == []

    status, body = call(api, "POST /api/friends/code", claims=ALA)
    assert status == 200 and body["code"] != code
    assert call(api, "GET /api/friends/code/{code}", claims=OLA, path={"code": code})[0] == 404


def test_decline_and_errors(api):
    invite(api, OLA, code_of(api, ALA))
    assert call(api, "DELETE /api/friends/requests/{userId}", claims=ALA, path={"userId": "user-2"}) == (200, {})
    assert call(api, "GET /api/friends", claims=ALA)[1]["incoming"] == []

    assert invite(api, ALA, code_of(api, ALA))[0] == 400
    assert invite(api, ALA, "WAW-222222") == (404, {"error": "Nie ma takiego kodu"})
    status, body = call(api, "POST /api/friends/invite", body={"code": 7}, claims=ALA)
    assert (status, body["fields"]) == (400, ["code"])
    assert call(api, "PUT /api/friends/requests/{userId}", claims=ALA, path={"userId": "nikt"})[0] == 404


def test_going_lists_friends_upcoming_only(api):
    befriend(api, OLA, ALA)
    invite(api, ZOSIA, code_of(api, ALA))  # zaproszenie bez akceptacji
    save(api, "e1", OLA)
    save(api, "yesterday", OLA)  # minione - znajomi nie widzą historii
    save(api, "saturday", BARTEK)  # nie-znajomy
    save(api, "saturday", ZOSIA)  # zaproszona, niezaakceptowana

    body = going(api)
    assert [card["id"] for card in body["items"]] == ["e1"]
    card = body["items"][0]
    assert card["friends"] == ["Ola"]
    assert (card["saves"], card["saved"], card["slot"]["start"]) == (1, False, "2026-10-15T18:00:00+02:00")
    assert body["byEvent"] == {"e1": ["Ola"]}
    assert "example.com" not in str(body)


def test_going_by_event_map(api):
    befriend(api, ALA, OLA)
    befriend(api, KUBA, ALA)
    save(api, "e1", OLA)
    save(api, "e1", KUBA)
    save(api, "saturday", KUBA)
    save(api, "e1", ALA)

    body = going(api)
    assert body["byEvent"] == {"e1": ["Kuba", "Ola"], "saturday": ["Kuba"]}
    assert [(c["id"], c["saved"], c["friends"]) for c in body["items"]] == [
        ("e1", True, ["Kuba", "Ola"]),
        ("saturday", False, ["Kuba"]),
    ]
    # po usunięciu znajomego jego wydarzenia znikają
    call(api, "DELETE /api/friends/{userId}", claims=ALA, path={"userId": KUBA["sub"]})
    assert going(api)["byEvent"] == {"e1": ["Ola"]}


def test_going_empty(api):
    assert going(api) == {"items": [], "byEvent": {}}


def test_attendees_mark_friends_first(api):
    befriend(api, ALA, OLA)
    befriend(api, KUBA, ALA)
    save(api, "e1", OLA)
    save(api, "e1", ALA)
    save(api, "e1", BARTEK)
    save(api, "e1", KUBA)
    save(api, "e1", ZOSIA)

    _, body = call(api, "GET /api/events/{id}/attendees", claims=ALA, path={"id": "e1"})
    assert body["people"] == [
        {"name": "Ala", "isMe": True, "isFriend": False},
        {"name": "Kuba", "isMe": False, "isFriend": True},
        {"name": "Ola", "isMe": False, "isFriend": True},
        {"name": "Zosia", "isMe": False, "isFriend": False},
        {"name": "Bartek", "isMe": False, "isFriend": False},
    ]


def test_attendees_past_event_hides_friends(api):
    befriend(api, ALA, OLA)
    save(api, "yesterday", ALA)
    save(api, "yesterday", OLA)  # znajomi nie widzą historii

    _, body = call(api, "GET /api/events/{id}/attendees", claims=ALA, path={"id": "yesterday"})
    assert [(p["name"], p["isFriend"]) for p in body["people"]] == [("Ala", False), ("Ola", False)]


def test_going_skips_classes_without_schedule(api):
    befriend(api, ALA, OLA)
    save(api, "no-schedule", OLA)  # zajęcia bez terminu - nie wiadomo, kiedy idzie
    assert going(api) == {"items": [], "byEvent": {}}


def test_remove_self_400(api):
    status, body = call(api, "DELETE /api/friends/{userId}", claims=ALA, path={"userId": ALA["sub"]})
    assert (status, body) == (400, {"error": "Nie możesz usunąć siebie"})


def test_unknown_friends_route_404(api):
    assert call(api, "PATCH /api/friends", claims=ALA)[0] == 404
