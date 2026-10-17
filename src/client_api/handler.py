"""API portalu klienta (HTTP API + JWT authorizer Cognito, payload 2.0).

    GET /api/me          profil zalogowanego użytkownika (pierwsze wywołanie zakłada rekord)
    GET /api/onboarding  pytania onboardingu (onboarding.py)
    PUT /api/profile     {"answers": {...}} -> walidacja, preferencje, zapis w tabeli users

Eksploruj, zapisy i Popularne (logika: events.py, DynamoDB: store.py). Karta (`Card`) = karta
rekomendacji z src/recommender_api/present.py bez reason/reasonSource/score, za to z
`saves` (liczba zapisanych) i `saved` (czy ja):

    GET    /api/events?when=today|tomorrow|weekend|week|date&date=RRRR-MM-DD&cat=sport|kultura|rekreacja
                       &district=&free=1&indoor=1&q=&limit=60 (maks. 200)
           -> {"when", "window": {"from", "to"}, "total", "items": [Card]}  (od najbliższego startu)
    GET    /api/events/stats?ids=a,b,c (maks. 100)   -> {"<id>": {"saves", "saved"}}
    GET    /api/events/{id}             -> Card + {"text" (bez HTML), "occurrences", "importedAt"}; 404
    PUT    /api/events/{id}/save        -> {"saved": true, "saves"}  (idempotentnie; 404 gdy brak wydarzenia)
    DELETE /api/events/{id}/save        -> {"saved": false, "saves"} (idempotentnie)
    GET    /api/events/{id}/attendees   -> {"saves", "saved", "people": [{"name", "isMe"}]}
                                           (najnowsi najpierw, maks. 100; bez imienia "Ktoś"; nigdy e-maili)
    GET    /api/popular                 -> {"window": {"from", "to"}, "items": [Card]}
                                           (dziś + 6 dni, saves > 0, malejąco, maks. 20)

Token weryfikuje API Gateway; tu korzystamy już tylko z jego claims (ID token Cognito).
Po zapisaniu profilu i przy logowaniu rekomender w tle liczy zestawy na dziś, jutro i weekend
(GET /api/recommendations obsługuje osobna Lambda: src/recommender_api).
"""

import json
import logging
import os
from datetime import date, datetime

import boto3

import events
import store
from codzis_common.http import ApiError, now_iso, parse_body, response
from onboarding import build_steps, compute_preferences, onboarding_version, public_steps, rag_profile, validate_answers

USERS_TABLE = os.environ["USERS_TABLE"]
POPULAR_LIMIT = 20
MAX_STATS_IDS = 100
MAX_NAME = 60
ANONYMOUS = "Ktoś"
DISTRICTS = json.loads(os.environ["DISTRICTS"])
RECOMMENDER_FUNCTION = os.environ.get("RECOMMENDER_FUNCTION")

STEPS = build_steps(DISTRICTS)
ONBOARDING_VERSION = onboarding_version(STEPS)

users = boto3.resource("dynamodb").Table(USERS_TABLE)
lambda_client = boto3.client("lambda")

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    try:
        match event.get("routeKey"):
            case "GET /api/me":
                return response(200, get_me(claims))
            case "GET /api/onboarding":
                return response(200, {"version": ONBOARDING_VERSION, "steps": public_steps(STEPS)})
            case "PUT /api/profile":
                return response(200, put_profile(claims, parse_body(event)))
            case "GET /api/events":
                return response(200, get_events(claims, _query(event)))
            case "GET /api/events/stats":
                return response(200, get_stats(claims, _query(event)))
            case "GET /api/events/{id}":
                return response(200, get_event(claims, _event_id(event)))
            case "PUT /api/events/{id}/save":
                return response(200, put_save(claims, _event_id(event)))
            case "DELETE /api/events/{id}/save":
                return response(200, delete_save(claims, _event_id(event)))
            case "GET /api/events/{id}/attendees":
                return response(200, get_attendees(claims, _event_id(event)))
            case "GET /api/popular":
                return response(200, get_popular(claims))
        raise ApiError(404, "Nie znaleziono")
    except ApiError as e:
        return response(e.status, e.body)


def get_me(claims: dict) -> dict:
    """Upsert danych z tokenu (e-mail, imię, dostawca) + ostatnie logowanie."""
    now = now_iso()
    values = {":now": now, ":provider": _provider(claims)}
    updates = ["lastLoginAt = :now", "createdAt = if_not_exists(createdAt, :now)", "identityProvider = :provider"]
    for attr, claim in (("email", "email"), ("displayName", "name"), ("picture", "picture")):
        if claims.get(claim):
            updates.append(f"{attr} = :{attr}")
            values[f":{attr}"] = claims[claim]

    item = users.update_item(
        Key={"userId": claims["sub"]},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )["Attributes"]
    if item.get("preferences"):
        _precompute(claims["sub"])  # liczy tylko brakujące lub nieaktualne zestawy
    return _view(item)


def put_profile(claims: dict, body: dict) -> dict:
    answers, errors = validate_answers(body.get("answers"), STEPS)
    if errors:
        raise ApiError(400, "Niepoprawne lub brakujące odpowiedzi", fields=errors)

    preferences = compute_preferences(answers, STEPS)
    now = now_iso()
    item = users.update_item(
        Key={"userId": claims["sub"]},
        UpdateExpression=(
            "SET onboarding = :onboarding, preferences = :preferences, ragProfile = :rag, "
            "updatedAt = :now, createdAt = if_not_exists(createdAt, :now)"
        ),
        ExpressionAttributeValues={
            ":onboarding": {"version": ONBOARDING_VERSION, "completedAt": now, "answers": answers},
            ":preferences": preferences,
            ":rag": rag_profile(preferences),
            ":now": now,
        },
        ReturnValues="ALL_NEW",
    )["Attributes"]
    _precompute(claims["sub"])  # nowe preferencje -> od razu nowe zestawy na dziś, jutro i weekend
    return _view(item)


def get_events(claims: dict, params: dict) -> dict:
    """Eksploruj: wszystko w oknie czasu, z filtrami, od najbliższego startu."""
    now = _now()
    filters, errors = events.parse_filters(params, events.warsaw_today(now), DISTRICTS)
    if filters is None:
        message = "Podaj dzień od dziś do 60 dni naprzód (RRRR-MM-DD)" if errors == ["date"] else "Niepoprawne filtry"
        raise ApiError(400, message, fields=errors)
    found = events.explore(list(store.all_events().values()), filters, now)
    page = found[: filters.limit]
    return {
        "when": filters.when,
        "window": _window(filters.date_from, filters.date_to),
        "total": len(found),
        "items": _cards(claims, page),
    }


def get_stats(claims: dict, params: dict) -> dict:
    """Liczniki dla kart rekomendacji: {id: {saves, saved}}."""
    ids = [i.strip() for i in (params.get("ids") or "").split(",") if i.strip()]
    if not ids or len(ids) > MAX_STATS_IDS:
        raise ApiError(400, f"Podaj od 1 do {MAX_STATS_IDS} identyfikatorów", fields=["ids"])
    counts = store.saves_for(ids)
    mine = store.saved_ids(claims["sub"])
    return {i: {"saves": counts[i], "saved": i in mine} for i in ids}


def get_event(claims: dict, event_id: str) -> dict:
    """Szczegóły: karta z najbliższym terminem + pełny opis bez HTML."""
    item = store.get_event(event_id)
    if not item:
        raise ApiError(404, "Nie znaleziono wydarzenia")
    slot = events.next_slot(item, now=_now())
    return events.detail(item, slot, store.saves_of(event_id), store.is_saved(event_id, claims["sub"]))


def put_save(claims: dict, event_id: str) -> dict:
    """Zapis na wydarzenie (kopiuje imię z tokenu). Ponowny zapis nic nie zmienia."""
    if not store.get_event(event_id):
        raise ApiError(404, "Nie znaleziono wydarzenia")
    store.save(event_id, claims["sub"], _name(claims), now_iso())
    return {"saved": True, "saves": store.saves_of(event_id)}


def delete_save(claims: dict, event_id: str) -> dict:
    """Wypisanie. Działa też dla wydarzeń, które już wygasły; ponowne nic nie zmienia."""
    store.unsave(event_id, claims["sub"])
    return {"saved": False, "saves": store.saves_of(event_id)}


def get_attendees(claims: dict, event_id: str) -> dict:
    """Lista zapisanych: tylko imiona (nigdy e-maile), najnowsi najpierw."""
    rows = store.attendees(event_id)
    me = claims["sub"]
    return {
        "saves": store.saves_of(event_id),
        "saved": store.is_saved(event_id, me),
        "people": [{"name": row.get("name") or ANONYMOUS, "isMe": row["userId"] == me} for row in rows],
    }


def get_popular(claims: dict) -> dict:
    """Wydarzenia z najbliższego tygodnia (dziś + 6 dni) z największą liczbą zapisanych.

    Indeks bySaves nie zna terminów, więc bierzemy zapas (store.POPULAR_FETCH) i filtrujemy:
    pomijamy wydarzenia spoza okna, już zakończone i te, których nie ma w codzis-events."""
    now = _now()
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
    return {"window": _window(date_from, date_to), "items": _cards(claims, page)}


def _cards(claims: dict, page: list[tuple[dict, dict]]) -> list[dict]:
    """Karty z licznikami z bazy (nie z pamięci) i stanem "Zapisano" użytkownika."""
    counts = store.saves_for(item["id"] for item, _ in page) if page else {}
    mine = store.saved_ids(claims["sub"]) if page else set()
    return [events.card(item, slot, counts[item["id"]], item["id"] in mine) for item, slot in page]


def _window(date_from: date, date_to: date) -> dict:
    return {"from": date_from.isoformat(), "to": date_to.isoformat()}


def _name(claims: dict) -> str | None:
    """Imię z ID tokenu (atrybut Cognito `name`); puste -> None (na listach "Ktoś")."""
    name = " ".join(str(claims.get("name") or "").split())[:MAX_NAME]
    return name or None


def _now() -> datetime:
    return datetime.now(events.WARSAW)


def _query(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


def _event_id(event: dict) -> str:
    event_id = (event.get("pathParameters") or {}).get("id") or ""
    if not event_id:
        raise ApiError(404, "Nie znaleziono wydarzenia")
    return event_id


def _precompute(user_id: str) -> None:
    """Asynchroniczne wywołanie rekomendera; odpowiedź nie czeka na liczenie."""
    if not RECOMMENDER_FUNCTION:
        return
    try:
        lambda_client.invoke(
            FunctionName=RECOMMENDER_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({"action": "precompute", "userId": user_id}),
        )
    except Exception:
        # Profil i tak jest zapisany; zestawy policzą się przy wejściu na stronę
        log.exception("Nie udało się zlecić przeliczenia rekomendacji")


def _view(item: dict) -> dict:
    onboarding = item.get("onboarding") or {}
    completed = bool(onboarding.get("completedAt"))
    return {
        "userId": item["userId"],
        "email": item.get("email"),
        "name": item.get("displayName"),
        "picture": item.get("picture"),
        "identityProvider": item.get("identityProvider"),
        "needsOnboarding": not completed,
        # pytania zmieniły się od ostatniego wypełnienia - warto poprosić o uzupełnienie
        "onboardingOutdated": completed and onboarding.get("version") != ONBOARDING_VERSION,
        "profile": {
            "answers": onboarding.get("answers", {}),
            "completedAt": onboarding.get("completedAt"),
            "preferences": item.get("preferences"),
            "ragProfile": item.get("ragProfile"),
        }
        if completed
        else None,
    }


def _provider(claims: dict) -> str:
    # Użytkownicy federacyjni mają claim "identities" (JSON jako tekst), np. [{"providerName": "Google", ...}]
    try:
        identities = json.loads(claims.get("identities") or "[]")
        if identities:
            return identities[0].get("providerName") or "Federated"
    except (TypeError, ValueError):
        pass
    return "Cognito"
