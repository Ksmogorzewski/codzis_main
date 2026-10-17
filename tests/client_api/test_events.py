"""Logika Eksploruj/Popularne bez AWS (src/client_api/events.py): karta, okna czasu, termin, filtry, pamięć."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tests.support import CLIENT_API_DIR, DISTRICTS, load_lambda

WARSAW = ZoneInfo("Europe/Warsaw")
# Środa w połowie tygodnia (tydzień: pon 12.10 - nd 18.10)
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=WARSAW)


@pytest.fixture(scope="module")
def ev():
    return load_lambda(CLIENT_API_DIR, "events")


def concert(**extra):
    record = {
        "id": "kal-concert",
        "origin": "um_warszawa",
        "source": "um_kalendarz",
        "kind": "event",
        "title": "<b>Koncert</b> jazzowy",
        "lead": "Wieczór &amp; muzyka",
        "text": "<p>Pełny <i>opis</i> &amp; więcej</p>",
        "url": "https://um.warszawa.pl/x",
        "imageUrl": "https://img/x.jpg",
        "district": "Śródmieście",
        "venue": {"name": "Klub Stodoła", "address": "Batorego 10"},
        "location": {"lat": Decimal("52.2"), "lon": Decimal("21.0")},
        "online": False,
        "occurrences": [{"start": "2026-10-14T19:00:00+02:00", "end": "2026-10-14T21:00:00+02:00", "allDay": False}],
        "attributes": {},
        "tags": {"theme": ["Muzyka"], "format": ["Koncert"], "cost": "Bezpłatne", "setting": "W pomieszczeniu"},
        "importedAt": "2026-10-14T03:00:00Z",
    }
    return record | extra


def yoga(**extra):
    record = {
        "id": "spt-yoga",
        "origin": "um_warszawa",
        "source": "um_sport",
        "kind": "recurring",
        "title": "Joga w parku",
        "district": "Mokotów",
        "schedule": [{"day": "saturday", "start": "10:00", "end": "11:00"}],
        "tags": {"theme": ["Rekreacja i fitness"], "cost": "Płatne", "setting": "Na zewnątrz"},
    }
    return record | extra


# --- karta ---


def test_card_maps_v1_event(ev):
    slot = {"start": "2026-10-14T19:00:00+02:00", "end": "2026-10-14T21:00:00+02:00", "allDay": False}
    card = ev.card(concert(), slot, saves=3, saved=True)

    assert card == {
        "id": "kal-concert",
        "title": "Koncert jazzowy",
        "lead": "Wieczór & muzyka",
        "url": "https://um.warszawa.pl/x",
        "ticketUrl": None,
        "imageUrl": "https://img/x.jpg",
        "origin": "um_warszawa",
        "source": "um_kalendarz",
        "kind": "event",
        "partnerName": None,
        "district": "Śródmieście",
        "venue": {"name": "Klub Stodoła", "address": "Batorego 10"},
        "location": {"lat": Decimal("52.2"), "lon": Decimal("21.0")},
        "online": False,
        "slot": slot,
        "schedule": [],
        "price": None,
        "tags": {"theme": ["Muzyka"], "format": ["Koncert"], "cost": "Bezpłatne", "setting": "W pomieszczeniu"},
        "saves": 3,
        "saved": True,
    }
    assert "reason" not in card and "score" not in card


def test_card_partner_price_ticket_and_recurring(ev):
    partner = concert(
        id="p-1",
        origin="partner",
        partnerName="Teatr X",
        attributes={"price": {"min": Decimal(20), "max": Decimal(40), "currency": "PLN"}, "ticketUrl": "https://t"},
        tags={"theme": ["Warsztaty"], "unknown_dim": ["x"], "audience": ["Dorośli (18-64)"]},
    )
    card = ev.card(partner, None, saves=0, saved=False)
    assert card["price"] == {"min": Decimal(20), "max": Decimal(40), "currency": "PLN"}
    assert card["ticketUrl"] == "https://t"
    assert card["partnerName"] == "Teatr X"
    assert card["tags"] == {"theme": ["Warsztaty"], "audience": ["Dorośli (18-64)"]}

    weekly = ev.card(yoga(), None, saves=0, saved=False)
    assert weekly["schedule"] == [{"day": "saturday", "start": "10:00", "end": "11:00"}]
    assert weekly["location"] is None and weekly["venue"] is None


def test_detail_has_plain_text_and_occurrences(ev):
    detail = ev.detail(concert(), None, saves=1, saved=False)
    assert detail["text"] == "Pełny opis & więcej"
    assert detail["occurrences"] == concert()["occurrences"]
    assert detail["importedAt"] == "2026-10-14T03:00:00Z"
    assert detail["saves"] == 1 and detail["saved"] is False


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"theme": ["Sport"]}, "sport"),
        ({"format": ["Zawody / turniej"], "theme": ["Muzyka"]}, "sport"),  # sport ma pierwszeństwo
        ({"theme": ["Historia"]}, "kultura"),
        ({"theme": ["Przyroda"]}, "rekreacja"),
        ({}, "rekreacja"),
    ],
)
def test_category_like_frontend(ev, tags, expected):
    assert ev.category_of(tags) == expected


# --- okna czasu ---


def test_windows(ev):
    wed = date(2026, 10, 14)
    assert ev.window("today", wed) == (wed, wed)
    assert ev.window("tomorrow", wed) == (date(2026, 10, 15), date(2026, 10, 15))
    assert ev.window("weekend", wed) == (date(2026, 10, 17), date(2026, 10, 18))
    assert ev.window("weekend", date(2026, 10, 18)) == (date(2026, 10, 18), date(2026, 10, 18))
    assert ev.window("week", wed) == (wed, date(2026, 10, 20))
    assert ev.window("date", wed, "2026-10-30") == (date(2026, 10, 30), date(2026, 10, 30))
    with pytest.raises(ValueError):
        ev.window("date", wed, "30.10.2026")
    with pytest.raises(ValueError):
        ev.window("date", wed, "2026-10-13")  # przeszłość


@pytest.mark.parametrize(
    ("today", "monday", "sunday"),
    [
        (date(2026, 10, 12), date(2026, 10, 12), date(2026, 10, 18)),  # poniedziałek
        (date(2026, 10, 18), date(2026, 10, 12), date(2026, 10, 18)),  # niedziela
        (date(2026, 10, 25), date(2026, 10, 19), date(2026, 10, 25)),  # niedziela zmiany czasu (CEST -> CET)
        (date(2026, 12, 31), date(2026, 12, 28), date(2027, 1, 3)),  # przełom roku
    ],
)
def test_current_week_monday_to_sunday(ev, today, monday, sunday):
    assert ev.current_week(today) == (monday, sunday)


def test_today_warsaw_uses_local_date_not_utc(ev):
    # 23:30 UTC w sobotę = 01:30 w niedzielę w Warszawie (CEST)
    utc_late = datetime.fromisoformat("2026-10-17T23:30:00+00:00")
    assert ev.warsaw_today(utc_late) == date(2026, 10, 18)


# --- termin (port next_slot z recommender/retriever/filters.py) ---


def test_next_slot_dated_event(ev):
    event = concert()
    assert ev.next_slot(event, date(2026, 10, 14), date(2026, 10, 14), NOW) == {
        "start": "2026-10-14T19:00:00+02:00",
        "end": "2026-10-14T21:00:00+02:00",
        "allDay": False,
    }
    # po zakończeniu: brak terminu
    late = datetime(2026, 10, 14, 21, 30, tzinfo=WARSAW)
    assert ev.next_slot(event, date(2026, 10, 14), date(2026, 10, 14), late) is None
    # poza oknem
    assert ev.next_slot(event, date(2026, 10, 15), date(2026, 10, 16), NOW) is None


def test_next_slot_without_end_lasts_two_hours(ev):
    event = {"occurrences": [{"start": "2026-10-14T11:00:00+02:00", "allDay": False}]}
    assert ev.next_slot(event, None, None, NOW) is not None  # 11:00 + 2 h > 12:00
    event = {"occurrences": [{"start": "2026-10-14T09:00:00+02:00", "allDay": False}]}
    assert ev.next_slot(event, None, None, NOW) is None


def test_next_slot_multi_day_exhibition_in_window(ev):
    event = {
        "occurrences": [{"start": "2026-10-01T10:00:00+02:00", "end": "2026-10-31T18:00:00+01:00", "allDay": False}]
    }
    slot = ev.next_slot(event, date(2026, 10, 17), date(2026, 10, 18), NOW)
    assert slot == {"start": "2026-10-01T10:00:00+02:00", "end": "2026-10-31T18:00:00+01:00", "allDay": False}


def test_next_slot_recurring(ev):
    assert ev.next_slot(yoga(), date(2026, 10, 17), date(2026, 10, 18), NOW) == {
        "recurring": True,
        "date": "2026-10-17",
        "day": "saturday",
        "start": "10:00",
        "end": "11:00",
    }
    assert ev.next_slot(yoga(), date(2026, 10, 14), date(2026, 10, 14), NOW) is None
    # zajęcia bez harmonogramu: dostępne, ale bez godziny
    assert ev.next_slot(yoga(schedule=[]), date(2026, 10, 14), date(2026, 10, 14), NOW) == {
        "recurring": True,
        "date": None,
        "day": None,
        "start": None,
        "end": None,
    }


def test_next_slot_recurring_late_arrival(ev):
    weekly = yoga(schedule=[{"day": "wednesday", "start": "11:45", "end": "13:00"}])
    today = date(2026, 10, 14)
    assert ev.next_slot(weekly, today, today, NOW) is not None  # 30 min spóźnienia
    weekly = yoga(schedule=[{"day": "wednesday", "start": "11:00", "end": "12:30"}])
    assert ev.next_slot(weekly, today, today, NOW) is None


# --- filtry ---


def parse(ev, **params):
    return ev.parse_filters(params, NOW.date(), DISTRICTS)


def test_parse_filters_defaults(ev):
    filters, errors = parse(ev)
    assert errors == []
    assert filters.when == "today"
    assert (filters.date_from, filters.date_to) == (NOW.date(), NOW.date())
    assert filters.cat is None and filters.district is None
    assert filters.free is False and filters.indoor is False
    assert filters.query == ""
    assert filters.limit == ev.DEFAULT_LIMIT


def test_parse_filters_errors(ev):
    _, errors = parse(ev, when="yesterday", cat="jedzenie", district="Gotham", limit="x")
    assert errors == ["when", "cat", "district", "limit"]
    _, errors = parse(ev, when="date", date="jutro")
    assert errors == ["date"]


def test_parse_filters_values(ev):
    filters, errors = parse(
        ev, when="weekend", cat="sport", district="Wola", free="true", indoor="1", q="  Jazz ", limit="500"
    )
    assert errors == []
    assert (filters.date_from, filters.date_to) == (date(2026, 10, 17), date(2026, 10, 18))
    assert filters.cat == "sport" and filters.district == "Wola"
    assert filters.free is True and filters.indoor is True
    assert filters.query == "jazz"
    assert filters.limit == ev.MAX_LIMIT


def explore_ids(ev, events, **params):
    filters, errors = parse(ev, **params)
    assert errors == []
    return [e["id"] for e, _ in ev.explore(events, filters, NOW)]


def test_explore_window_and_sorting(ev):
    events = [
        yoga(),
        concert(),
        concert(id="early", occurrences=[{"start": "2026-10-14T13:00:00+02:00", "allDay": False}]),
        concert(id="over", occurrences=[{"start": "2026-10-14T08:00:00+02:00", "end": "2026-10-14T09:00:00+02:00"}]),
        yoga(id="no-schedule", schedule=[]),
    ]
    # bez harmonogramu na końcu (nie wiadomo kiedy)
    assert explore_ids(ev, events) == ["early", "kal-concert", "no-schedule"]
    assert explore_ids(ev, events, when="weekend") == ["spt-yoga", "no-schedule"]


def test_explore_filters(ev):
    events = [concert(), yoga(schedule=[{"day": "wednesday", "start": "18:00"}])]
    assert explore_ids(ev, events, cat="kultura") == ["kal-concert"]
    assert explore_ids(ev, events, cat="sport") == ["spt-yoga"]
    assert explore_ids(ev, events, district="Mokotów") == ["spt-yoga"]
    assert explore_ids(ev, events, free="1") == ["kal-concert"]
    assert explore_ids(ev, events, indoor="1") == ["kal-concert"]
    assert explore_ids(ev, events, q="stodola") == ["kal-concert"]  # bez polskich znaków, po miejscu
    assert explore_ids(ev, events, q="JOGA park") == ["spt-yoga"]  # wszystkie słowa
    assert explore_ids(ev, events, q="joga koncert") == []


def test_explore_indoor_accepts_mixed_setting(ev):
    mixed = concert(tags={"setting": "W pomieszczeniu i na zewnątrz"})
    assert explore_ids(ev, [mixed], indoor="1") == ["kal-concert"]


def test_explore_skips_records_without_title(ev):
    assert explore_ids(ev, [concert(title="")]) == []


# --- pamięć podręczna scanu ---


def test_event_cache_ttl(ev):
    loads = []

    def load():
        loads.append(1)
        return {"a": {"id": "a"}, "n": len(loads)}

    cache = ev.EventCache(load, ttl=300)
    assert cache.get(now=1000.0)["n"] == 1
    assert cache.get(now=1299.0)["n"] == 1  # jeszcze świeże
    assert cache.get(now=1300.0)["n"] == 2  # minęło 5 min
    assert len(loads) == 2
