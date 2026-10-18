"""Trasy Eksploruj i Popularne: /api/events (+ /stats, /{id}), /api/popular (logika: events.py, dane: store.py)."""

from datetime import date

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter

import events
import profiles
import store
from codzis_common.app import ApiError, parse_input
from routes import common
from schemas import MAX_STATS_IDS, EventsQuery, StatsQuery

POPULAR_LIMIT = 20
EVENT_NOT_FOUND = "Nie znaleziono wydarzenia"
FILTERS_ERROR = "Niepoprawne filtry"
DAY_ERROR = "Podaj dzień od dziś do 60 dni naprzód (RRRR-MM-DD)"

router = APIGatewayHttpRouter()


@router.get("/api/events")
def get_events() -> dict:
    """Eksploruj: wszystko w oknie czasu, z filtrami, od najbliższego startu."""
    user = common.claims(router)
    params = parse_input(EventsQuery, common.query(router), FILTERS_ERROR)
    now = common.now()
    filters, errors = events.parse_filters(params.model_dump(), events.warsaw_today(now), profiles.DISTRICTS)
    if filters is None:
        raise ApiError(400, DAY_ERROR if errors == ["date"] else FILTERS_ERROR, fields=errors)
    found = events.explore(list(store.all_events().values()), filters, now)
    page = found[: filters.limit]
    return {
        "when": filters.when,
        "window": _window(filters.date_from, filters.date_to),
        "total": len(found),
        "items": common.cards(user, page),
    }


@router.get("/api/events/stats")
def get_stats() -> dict:
    """Liczniki dla kart rekomendacji: {id: {saves, saved}}."""
    user_id = common.claims(router)["sub"]
    ids = parse_input(StatsQuery, common.query(router), f"Podaj od 1 do {MAX_STATS_IDS} identyfikatorów").ids
    counts = store.saves_for(ids)
    mine = store.saved_ids(user_id)
    return {i: {"saves": counts[i], "saved": i in mine} for i in ids}


@router.get("/api/events/<id>")
def get_event(id: str) -> dict:
    """Szczegóły: karta z najbliższym terminem + pełny opis bez HTML."""
    user_id = common.claims(router)["sub"]
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    item = store.get_event(event_id)
    if not item:
        raise ApiError(404, EVENT_NOT_FOUND)
    slot = events.next_slot(item, now=common.now())
    return events.detail(item, slot, store.saves_of(event_id), store.is_saved(event_id, user_id))


@router.get("/api/popular")
def get_popular() -> dict:
    """Wydarzenia z najbliższego tygodnia (dziś + 6 dni) z największą liczbą zapisanych.

    Indeks bySaves nie zna terminów, więc bierzemy zapas (store.POPULAR_FETCH) i filtrujemy:
    pomijamy wydarzenia spoza okna, już zakończone i te, których nie ma w codzis-events."""
    user = common.claims(router)
    now = common.now()
    date_from, date_to = events.window("week", events.warsaw_today(now))
    known = store.all_events()
    page: list[tuple[dict, dict]] = []
    for event_id in store.top_saved():
        item = known.get(event_id)
        slot = events.next_slot(item, date_from, date_to, now) if item else None
        if item and slot:
            page.append((item, slot))
        if len(page) == POPULAR_LIMIT:
            break
    return {"window": _window(date_from, date_to), "items": common.cards(user, page)}


def _window(date_from: date, date_to: date) -> dict:
    return {"from": date_from.isoformat(), "to": date_to.isoformat()}
