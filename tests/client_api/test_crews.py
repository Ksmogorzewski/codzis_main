"""Czat ekipy (src/client_api/crews.py, trasy /api/events/{id}/crew i /api/me/crews) na atrapie DynamoDB."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.client_api.conftest import call

WARSAW = ZoneInfo("Europe/Warsaw")
START = datetime(2026, 10, 14, 12, 0, tzinfo=WARSAW)
JAZZ_END = int(datetime(2026, 10, 21, 21, 0, tzinfo=WARSAW).timestamp())  # expiresAt z taggera
DAY = 24 * 3600


def person(n, name, family):
    return {"sub": f"user-{n}", "email": f"u{n}@example.com", "name": name, "family_name": family}


ALA = person(1, "Ala", "Nowak")
BARTEK = person(2, "Bartek", "Zieliński")
CELINA = person(3, "Celina", "Kowalska")
DAREK = person(4, "Darek", "Wiśniewski")
ELA = person(5, "Ela", "Lis")
NONAME = {"sub": "user-9", "email": "anon@example.com"}


class Clock:
    """Czas handlera: każda akcja w testach przesuwa go o kilka sekund (kolejność wiadomości, limit 1 s)."""

    def __init__(self):
        self.now = START

    def tick(self, seconds=2.0):
        self.now += timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock(client_api, monkeypatch):
    c = Clock()
    monkeypatch.setattr(client_api, "_now", lambda: c.now)
    return c


def event(event_id, title, **extra):
    return {
        "id": event_id,
        "origin": "um_warszawa",
        "source": "um_kalendarz",
        "kind": "event",
        "title": title,
        "district": "Wola",
        "occurrences": [{"start": "2026-10-20T19:00:00+02:00", "allDay": False}],
        "tags": {"theme": ["Muzyka"], "cost": "Bezpłatne"},
    } | extra


@pytest.fixture
def api(client_api, clock, events_table):
    events_table.put_item(Item=event("jazz", "Koncert <b>jazzowy</b>", expiresAt=JAZZ_END))
    events_table.put_item(Item=event("kino", "Kino plenerowe"))  # bez expiresAt (bez końca)
    return client_api


def save(api, claims, event_id="jazz"):
    status, _ = call(api, "PUT /api/events/{id}/save", claims=claims, path={"id": event_id})
    assert status == 200


def unsave(api, claims, event_id="jazz"):
    status, _ = call(api, "DELETE /api/events/{id}/save", claims=claims, path={"id": event_id})
    assert status == 200


def chat(api, claims, event_id="jazz", after=None):
    return call(
        api,
        "GET /api/events/{id}/crew",
        claims=claims,
        path={"id": event_id},
        query={"after": after} if after else None,
    )


def open_chat(api, clock, claims, event_id="jazz"):
    """Zapis + wejście na czat (dołączenie do ekipy)."""
    clock.tick()
    save(api, claims, event_id)
    status, body = chat(api, claims, event_id)
    assert status == 200, body
    return body


def send(api, clock, claims, text, event_id="jazz"):
    clock.tick()
    return call(api, "POST /api/events/{id}/crew/messages", {"text": text}, claims=claims, path={"id": event_id})


def my_crews(api, claims):
    status, body = call(api, "GET /api/me/crews", claims=claims)
    assert status == 200
    return body


def kinds(body):
    return [m["kind"] for m in body["messages"]]


# --- czyste funkcje ---


def test_clean_message(crews):
    assert crews.clean_message("  Cześć\tekipo!  ") == "Cześć ekipo!"
    assert crews.clean_message("a\r\n\r\n\r\n\nb\n c ") == "a\n\nb\nc"  # najwyżej jedna pusta linia
    assert crews.clean_message("zły‮tekst\x00") == "złytekst"  # zmiana kierunku i sterujące znikają
    assert crews.clean_message("👩‍👩‍👧 rodzinka") == "👩‍👩‍👧 rodzinka"  # emoji z łącznikiem zostają
    assert crews.clean_message(5) == ""
    assert crews.clean_message(None) == ""


def test_icebreaker_is_stable_per_crew(crews):
    first = crews.icebreaker("jazz", "001")
    assert first in crews.ICEBREAKERS
    assert crews.icebreaker("jazz", "001") == first
    assert len({crews.icebreaker(f"e{i}", "001") for i in range(40)}) > 1


def test_iso_and_ttl(crews):
    assert crews.iso(datetime(2026, 10, 14, 12, 0, 0, 123000, tzinfo=WARSAW)) == "2026-10-14T10:00:00.123Z"
    now = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
    assert crews.expires_at({"expiresAt": JAZZ_END}, now) == JAZZ_END + 30 * DAY
    assert crews.expires_at({}, now) == int(now.timestamp()) + 30 * DAY  # bez końca: od teraz
    assert crews.expires_at({"expiresAt": 100}, now) == int(now.timestamp()) + 30 * DAY  # już po końcu


# --- dołączanie do ekipy ---


def test_first_visit_creates_crew_with_welcome(api, clock, crews):
    body = open_chat(api, clock, ALA)

    assert body["crew"] == "001"
    assert body["capacity"] == 4
    assert body["members"] == [{"userId": "user-1", "name": "Ala N.", "isMe": True}]
    assert body["messageCount"] == 1
    assert body["answered"] is False
    assert body["icebreaker"] == crews.icebreaker("jazz", "001")
    [welcome] = body["messages"]
    assert (welcome["kind"], welcome["userId"], welcome["name"], welcome["isMe"]) == (
        "welcome",
        "user-1",
        "Ala N.",
        True,
    )
    assert welcome["text"] is None
    assert body["cursor"] == welcome["sentAt"]


def test_crew_fills_up_to_four_then_next_crew_starts(api, clock):
    for claims in (ALA, BARTEK, CELINA):
        open_chat(api, clock, claims)
    darek = open_chat(api, clock, DAREK)

    assert [m["name"] for m in darek["members"]] == ["Ala N.", "Bartek Z.", "Celina K.", "Darek W."]
    assert kinds(darek) == ["welcome", "joined", "joined", "joined", "full"]
    assert darek["messageCount"] == 5

    ela = open_chat(api, clock, ELA)
    assert ela["crew"] == "002"
    assert [m["userId"] for m in ela["members"]] == ["user-5"]
    assert kinds(ela) == ["welcome"]


def test_next_visits_keep_the_same_crew(api, clock):
    first = open_chat(api, clock, ALA)
    clock.tick()
    _, again = chat(api, ALA)
    assert again["crew"] == first["crew"]
    assert again["messageCount"] == 1


def test_crews_are_per_event(api, clock):
    open_chat(api, clock, ALA)
    kino = open_chat(api, clock, BARTEK, "kino")
    assert kino["crew"] == "001"
    assert [m["userId"] for m in kino["members"]] == ["user-2"]


def test_chat_only_for_attendees(api, clock):
    status, body = chat(api, ALA)
    assert status == 409
    assert body["code"] == "not_attending"

    status, _ = call(api, "POST /api/events/{id}/crew/messages", {"text": "hej"}, claims=ALA, path={"id": "jazz"})
    assert status == 409

    assert chat(api, ALA, "nie-ma")[0] == 404


def test_chat_requires_name(api, clock):
    save(api, NONAME)
    status, body = chat(api, NONAME)
    assert status == 409
    assert body == {"error": "Podaj imię, zanim dołączysz do ekipy", "code": "name_required"}


def test_member_record_is_repaired_without_changing_crew(api, clock, crews_table):
    open_chat(api, clock, ALA)
    open_chat(api, clock, BARTEK)
    crews_table.delete_item(Key={"eventId": "jazz", "sk": "member#user-2"})  # np. wygasł wcześniej niż ekipa

    _, body = chat(api, BARTEK)

    assert body["crew"] == "001"
    assert [m["userId"] for m in body["members"]] == ["user-1", "user-2"]
    assert kinds(body) == ["welcome", "joined"]  # bez drugiego „dołącza”
    assert crews_table.get_item(Key={"eventId": "jazz", "sk": "member#user-2"})["Item"]["crew"] == "001"


def test_parallel_join_never_overfills_a_crew(api, clock, crews, monkeypatch):
    for claims in (ALA, BARTEK, CELINA):
        open_chat(api, clock, claims)
    stale = crews._rows("jazz", "crew#")  # Ela widzi ekipę 001 z 3 osobami...
    open_chat(api, clock, DAREK)  # ...ale Darek zajmuje ostatnie miejsce przed nią

    real_rows = crews._rows
    calls = []

    def rows(event_id, prefix):
        calls.append(prefix)
        return stale if len(calls) == 1 else real_rows(event_id, prefix)

    monkeypatch.setattr(crews, "_rows", rows)
    ela = open_chat(api, clock, ELA)

    assert len(calls) == 2  # warunek liczby osób nie przeszedł -> druga próba na świeżym stanie
    assert ela["crew"] == "002"
    _, darek = chat(api, DAREK)
    assert len(darek["members"]) == 4


def test_ttl_follows_event_end(api, clock, crews_table):
    open_chat(api, clock, ALA)
    open_chat(api, clock, ALA, "kino")

    items = crews_table.scan()["Items"]
    assert {i["expiresAt"] for i in items if i["eventId"] == "jazz"} == {JAZZ_END + 30 * DAY}
    assert {i["expiresAt"] for i in items if i["eventId"] == "kino"} == {int(clock.now.timestamp()) + 30 * DAY}


# --- wiadomości ---


def test_messages_reach_my_crew_only(api, clock):
    for claims in (ALA, BARTEK, CELINA, DAREK):
        open_chat(api, clock, claims)
    open_chat(api, clock, ELA)  # ekipa 002

    status, body = send(api, clock, ALA, "Spotykamy się przy wejściu?")
    assert status == 200
    sent = body["message"]
    assert (sent["kind"], sent["name"], sent["text"], sent["isMe"]) == (
        "user",
        "Ala N.",
        "Spotykamy się przy wejściu?",
        True,
    )

    _, bartek = chat(api, BARTEK)
    assert bartek["messages"][-1] == sent | {"isMe": False}
    _, ela = chat(api, ELA)
    assert kinds(ela) == ["welcome"]


def test_first_message_unlocks_chat(api, clock):
    assert open_chat(api, clock, ALA)["answered"] is False
    send(api, clock, ALA, "Plac Zbawiciela!")
    _, body = chat(api, ALA)
    assert body["answered"] is True


def test_message_text_is_validated(api, clock, crews):
    open_chat(api, clock, ALA)
    for bad in ["", "   \n\t ", None, 12, "x" * 501]:
        status, body = send(api, clock, ALA, bad)
        assert (status, body["fields"]) == (400, ["text"]), bad
    status, body = send(api, clock, ALA, "  Cześć\n\n\n\nekipo ‮ ")
    assert status == 200
    assert body["message"]["text"] == "Cześć\n\nekipo"
    assert send(api, clock, ALA, "y" * 500)[0] == 200


def test_sending_too_fast_is_limited(api, clock):
    open_chat(api, clock, ALA)
    assert send(api, clock, ALA, "Raz")[0] == 200

    clock.tick(-1.5)  # druga wiadomość 0,5 s po pierwszej
    status, body = send(api, clock, ALA, "Dwa")
    assert (status, body["code"]) == (429, "too_fast")

    assert send(api, clock, ALA, "Trzy")[0] == 200


def test_after_returns_new_messages_with_overlap(api, clock):
    open_chat(api, clock, ALA)
    open_chat(api, clock, BARTEK)
    _, first = chat(api, ALA)
    cursor = first["cursor"]

    clock.tick(30)
    _, sent = send(api, clock, BARTEK, "Jestem już na miejscu")
    clock.tick()
    _, page = chat(api, ALA, after=cursor)

    ids = [m["id"] for m in page["messages"]]
    assert sent["message"]["id"] in ids
    since = datetime.fromisoformat(cursor) - timedelta(seconds=15)
    assert all(datetime.fromisoformat(m["sentAt"]) >= since for m in page["messages"])
    assert page["cursor"] == sent["message"]["sentAt"]

    # nic nowego: pusta lista (poza zapasem 15 s) i ten sam cursor
    clock.tick(60)
    _, idle = chat(api, ALA, after=page["cursor"])
    assert idle["messages"] == [m for m in idle["messages"] if m["id"] == sent["message"]["id"]]
    assert idle["cursor"] == page["cursor"]


def test_bad_after_is_rejected(api, clock):
    open_chat(api, clock, ALA)
    for bad in ["wczoraj", "2026-10-14T10:00:00"]:  # bez strefy też nie
        status, body = chat(api, ALA, after=bad)
        assert (status, body["fields"]) == (400, ["after"])


def test_long_history_returns_newest_page(api, clock, crews, monkeypatch):
    monkeypatch.setattr(crews, "PAGE", 3)
    open_chat(api, clock, ALA)
    for i in range(5):
        send(api, clock, ALA, f"wiadomość {i}")
    _, body = chat(api, ALA)
    assert [m["text"] for m in body["messages"]] == ["wiadomość 2", "wiadomość 3", "wiadomość 4"]
    assert body["messageCount"] == 6


# --- nieprzeczytane i plakietki ---


def test_unread_counts_and_reading(api, clock):
    open_chat(api, clock, ALA)
    open_chat(api, clock, BARTEK)  # Ala: +1 („Bartek dołącza”)
    send(api, clock, BARTEK, "Hej!")
    send(api, clock, BARTEK, "Kto będzie pierwszy?")

    mine = my_crews(api, ALA)
    [item] = mine["items"]
    assert mine["unread"] == 3
    assert (item["eventId"], item["title"], item["crew"], item["unread"], item["messageCount"]) == (
        "jazz",
        "Koncert jazzowy",
        "001",
        3,
        4,
    )
    assert [m["name"] for m in item["members"]] == ["Ala N.", "Bartek Z."]
    assert item["last"] == {
        "kind": "user",
        "userId": "user-2",
        "name": "Bartek Z.",
        "text": "Kto będzie pierwszy?",
        "sentAt": item["last"]["sentAt"],
        "isMe": False,
    }
    assert my_crews(api, BARTEK)["unread"] == 0  # własne wiadomości są przeczytane

    chat(api, ALA)  # otwarty czat = wszystko przeczytane
    assert my_crews(api, ALA)["unread"] == 0


def test_my_crews_only_events_with_my_crew(api, clock):
    save(api, ALA, "kino")  # zapis bez wejścia na czat - jeszcze bez ekipy
    assert my_crews(api, ALA) == {"items": [], "unread": 0}
    open_chat(api, clock, ALA)
    assert [i["eventId"] for i in my_crews(api, ALA)["items"]] == ["jazz"]


def test_last_message_preview_is_one_short_line(api, clock):
    open_chat(api, clock, ALA)
    send(api, clock, ALA, "Pierwsza linia\n" + "x" * 300)
    [item] = my_crews(api, ALA)["items"]
    assert "\n" not in item["last"]["text"]
    assert len(item["last"]["text"]) == 140
    assert item["last"]["text"].endswith("…")


# --- wyjście z ekipy (wypisanie z wydarzenia) ---


def test_unsave_leaves_crew_and_frees_the_spot(api, clock):
    for claims in (ALA, BARTEK, CELINA, DAREK):
        open_chat(api, clock, claims)
    send(api, clock, DAREK, "Będę z aparatem")

    clock.tick()
    unsave(api, DAREK)
    assert chat(api, DAREK)[0] == 409
    assert my_crews(api, DAREK)["items"] == []

    ela = open_chat(api, clock, ELA)
    assert ela["crew"] == "001"  # zwolnione miejsce
    assert [m["userId"] for m in ela["members"]] == ["user-1", "user-2", "user-3", "user-5"]
    assert kinds(ela)[-4:] == ["user", "left", "joined", "full"]
    assert ela["messages"][-4]["text"] == "Będę z aparatem"  # wiadomości osoby, która wyszła, zostają
    assert ela["messages"][-3]["name"] == "Darek W."


def test_unsave_is_idempotent_and_works_without_crew(api, clock):
    save(api, ALA)
    unsave(api, ALA)  # zapisana, ale bez ekipy
    open_chat(api, clock, BARTEK)
    clock.tick()
    unsave(api, BARTEK)
    unsave(api, BARTEK)


def test_last_person_leaving_closes_crew(api, clock):
    open_chat(api, clock, ALA)
    clock.tick()
    unsave(api, ALA)

    bartek = open_chat(api, clock, BARTEK)
    assert bartek["crew"] == "002"  # nikt nie dołącza do pustej rozmowy obcych osób
    assert kinds(bartek) == ["welcome"]


def test_back_after_unsave_starts_fresh_membership(api, clock):
    open_chat(api, clock, ALA)
    open_chat(api, clock, BARTEK)
    send(api, clock, ALA, "Hej")
    clock.tick()
    unsave(api, ALA)

    again = open_chat(api, clock, ALA)
    assert again["crew"] == "001"
    assert again["answered"] is False  # nowe wejście = znów lodołamacz
    assert kinds(again)[-2:] == ["left", "joined"]
