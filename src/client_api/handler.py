"""API portalu klienta (HTTP API + JWT authorizer Cognito, payload 2.0).

    GET    /api/me          profil zalogowanego użytkownika (pierwsze wywołanie zakłada rekord i dane konta;
                            kopiuje z tokenu e-mail, imię -> displayName, nazwisko -> familyName)
    PUT    /api/me          {"birthDate"} -> dane konta (account.py); imię i nazwisko zostają bez zmian. Przy
                            wypełnionej ankiecie przelicza też preferencje (przedział wieku z daty urodzenia)
    POST   /api/me/photo    {"contentType"} -> {"key", "upload": {"url", "fields"}} (presigned POST do S3)
    PUT    /api/me/photo    {"key"} -> wgrane zdjęcie staje się zdjęciem profilowym (poprzednie usuwamy)
    DELETE /api/me/photo    -> profil bez zdjęcia
    GET    /api/onboarding  pytania onboardingu (onboarding.py)
    PUT    /api/profile     {"answers": {...}} -> walidacja, preferencje (+ przedział wieku z account.birthDate),
                            zapis w tabeli users

Odpowiedź tras /api/me = GET /api/me: m.in. "name" (imię), "familyName" (nazwisko - tylko dla właściciela),
"account": {"birthDate", "photoUrl"}.

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
    GET    /api/events/{id}/attendees   -> {"saves", "saved", "people": [{"userId", "name", "isMe", "isFriend"}]}
                                           (najpierw ja, potem znajomi, potem reszta - w grupach najnowsi
                                           najpierw; isFriend tylko dla wydarzeń z nadchodzącym terminem,
                                           inaczej false; maks. 100 najnowszych; bez imienia "Ktoś"; nigdy e-maili;
                                           userId = sub z Cognito, dane testowe "seed-<n>" - tożsamość osoby)
    GET    /api/popular                 -> {"window": {"from", "to"}, "items": [Card]}
                                           (dziś + 6 dni, saves > 0, malejąco, maks. 20)
    GET    /api/me/events               -> {"items": [Card + {"past", "savedAt"}]}  zakładka „Twoje”: moje zapisy
                                           (saved = true; najpierw nadchodzące od najbliższego terminu, potem
                                           minione - past = true, slot = ostatni termin - od najświeższego;
                                           maks. 100 najnowszych zapisów; bez wydarzeń wygasłych z codzis-events)

Imię widoczne dla innych (zapisy, zaproszenia, znajomi, podgląd kodu) składa display_name: imię + inicjał
nazwiska („Ola K.”, nazwisko opcjonalne przy rejestracji); pełnego nazwiska nie oddajemy nikomu.

Znajomi (logika i DynamoDB: friends.py). Akcje oznaczone (imię) bez imienia w tokenie i w users ->
409 {"code": "name_required"}. Czasy createdAt/since: ISO 8601 UTC. userId = sub z Cognito (nigdy e-mail):

    GET    /api/friends (imię)             -> {"code": "WAW-XXXXXX", "friends": [{"userId", "name", "since"}],
                                              "incoming": [{"userId", "name", "createdAt"}], "outgoing": [...]}
                                              (pierwsze wywołanie zakłada kod; znajomi alfabetycznie,
                                              zaproszenia najnowsze najpierw, wygasłe po 30 dniach pominięte)
    POST   /api/friends/code (imię)        -> {"code"}  nowy kod (stary przestaje działać; znajomi
                                              i oczekujące zaproszenia zostają)
    GET    /api/friends/code/{code}        -> {"userId", "name"}  do kogo należy kod (wpis "byle jak":
                                              "waw 7k2p9x" = "WAW-7K2P9X"); 404 zły kod, 400 własny kod
    POST   /api/friends/invite (imię)      {"code"} -> {"status": "pending" | "friends", "userId", "name"}
                                              ("friends": już znajomi albo ta osoba już mnie zaprosiła -
                                              automatyczna akceptacja); 404, 400 jak wyżej
    PUT    /api/friends/requests/{userId} (imię) -> {"status": "friends"}  akceptacja; 404 brak zaproszenia
    DELETE /api/friends/requests/{userId}  -> {}  ciche odrzucenie (zapraszający dalej widzi "oczekuje")
    DELETE /api/friends/{userId}           -> {}  usunięcie znajomości u obu stron; własne id -> 400
    GET    /api/friends/going              -> {"items": [Card + {"friends": [Friend]}], "byEvent": {eventId: [Friend]}}
                                              Friend = {"userId", "name"}; nadchodzące zapisy znajomych (od teraz;
                                              bez zajęć bez terminu); karty od najbliższego startu, maks. 60;
                                              byEvent - wszystkie; znajomi po imieniu, potem po userId
    Błędy: 404 zły kod (+1 do limitu), 429 {"code": "too_many_attempts"} po 10 złych kodach w godzinę
    (także dobre kody do końca okna), 409 {"code": "friend_limit"} przy 50 znajomych.

Token weryfikuje API Gateway; tu korzystamy już tylko z jego claims (ID token Cognito).
Po zapisaniu profilu i przy logowaniu rekomender w tle liczy zestawy na dziś, jutro i weekend
(GET /api/recommendations obsługuje osobna Lambda: src/recommender_api).
"""

import json
import logging
import os
import re
from datetime import date, datetime

import boto3

import account
import events
import friends
import store
from codzis_common.aws import AWS_CONFIG
from codzis_common.http import ApiError, handle_request, now_iso, parse_body, response
from onboarding import (
    build_steps,
    compute_preferences,
    onboarding_version,
    public_steps,
    rag_profile,
    validate_answers,
    with_age,
)

USERS_TABLE = os.environ["USERS_TABLE"]
POPULAR_LIMIT = 20
MY_EVENTS_LIMIT = 100
MAX_STATS_IDS = 100
MAX_NAME = 60
GOING_LIMIT = 60
ANONYMOUS = "Ktoś"
DISTRICTS = json.loads(os.environ["DISTRICTS"])
RECOMMENDER_FUNCTION = os.environ.get("RECOMMENDER_FUNCTION")

STEPS = build_steps(DISTRICTS)
ONBOARDING_VERSION = onboarding_version(STEPS)

users = boto3.resource("dynamodb", config=AWS_CONFIG).Table(USERS_TABLE)
lambda_client = boto3.client("lambda", config=AWS_CONFIG)

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event, context):
    """Punkt wejścia: każdy błąd kończy się odpowiedzią JSON (inny niż ApiError -> 500 z requestId)."""
    return handle_request(event, event.get("routeKey"), lambda: route(event))


def route(event: dict) -> dict:
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    match event.get("routeKey"):
        case "GET /api/me":
            return response(200, get_me(claims))
        case "PUT /api/me":
            return response(200, put_me(claims, parse_body(event)))
        case "POST /api/me/photo":
            return response(200, post_photo(claims, parse_body(event)))
        case "PUT /api/me/photo":
            return response(200, put_photo(claims, parse_body(event)))
        case "DELETE /api/me/photo":
            return response(200, delete_photo(claims))
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
        case "GET /api/me/events":
            return response(200, get_my_events(claims))
        case "GET /api/friends":
            return response(200, get_friends(claims))
        case "POST /api/friends/code":
            return response(200, {"code": friends.regenerate_code(claims["sub"], _require_name(claims))})
        case "GET /api/friends/code/{code}":
            return response(200, friends.preview(claims["sub"], _path(event, "code"), _epoch()))
        case "POST /api/friends/invite":
            return response(200, post_invite(claims, parse_body(event)))
        case "PUT /api/friends/requests/{userId}":
            return response(200, put_friend_request(claims, _path(event, "userId")))
        case "DELETE /api/friends/requests/{userId}":
            friends.decline(claims["sub"], _path(event, "userId"))
            return response(200, {})
        case "DELETE /api/friends/{userId}":
            friends.remove(claims["sub"], _path(event, "userId"))
            return response(200, {})
        case "GET /api/friends/going":
            return response(200, get_friends_going(claims))
    raise ApiError(404, "Nie znaleziono")


def get_me(claims: dict) -> dict:
    """Upsert danych z tokenu (e-mail, imię, dostawca) + ostatnie logowanie; dane konta tylko za pierwszym razem."""
    now = now_iso()
    values = {":now": now, ":provider": _provider(claims), ":account": account.prefill(claims)}
    updates = [
        "lastLoginAt = :now",
        "createdAt = if_not_exists(createdAt, :now)",
        "identityProvider = :provider",
        "#account = if_not_exists(#account, :account)",
    ]
    copies = (("email", "email"), ("displayName", "name"), ("familyName", "family_name"), ("picture", "picture"))
    for attr, claim in copies:
        if claims.get(claim):
            updates.append(f"{attr} = :{attr}")
            values[f":{attr}"] = claims[claim]

    item = users.update_item(
        Key={"userId": claims["sub"]},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeNames={"#account": "account"},
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

    preferences = _preferences(answers, _account(claims["sub"]).get("birthDate"))
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


def put_me(claims: dict, body: dict) -> dict:
    """Data urodzenia w profilu (imię i nazwisko zostają z rejestracji albo Google). Z daty liczymy przedział
    wieku w preferencjach, więc przy wypełnionej ankiecie przeliczamy też preferencje i profil RAG."""
    values, errors = account.validate(body, events.warsaw_today(_now()))
    if errors:
        raise ApiError(400, "Niepoprawne dane profilu", fields=errors)
    user = (
        users.get_item(
            Key={"userId": claims["sub"]},
            ProjectionExpression="#account, onboarding, preferences",
            ExpressionAttributeNames={"#account": "account"},
        ).get("Item")
        or {}
    )
    value = account.merge(user.get("account") or {}, values)
    onboarding = user.get("onboarding") or {}
    preferences = None
    if onboarding.get("completedAt"):
        preferences = _preferences(onboarding.get("answers") or {}, value.get("birthDate"))
    me = _save_account(claims["sub"], value, preferences)
    if preferences is not None and preferences != user.get("preferences"):
        _precompute(claims["sub"])  # inny przedział wieku -> nowe zestawy rekomendacji
    return me


def post_photo(claims: dict, body: dict) -> dict:
    """Formularz uploadu zdjęcia prosto do S3; profil zmienia dopiero PUT /api/me/photo."""
    content_type = body.get("contentType")
    if content_type not in account.PHOTO_TYPES:
        raise ApiError(400, "Zdjęcie musi być w formacie JPG, PNG albo WebP", fields=["contentType"])
    return account.upload_form(claims["sub"], content_type)


def put_photo(claims: dict, body: dict) -> dict:
    key = body.get("key")
    if not (account.own_photo_key(key, claims["sub"]) and account.uploaded(key)):
        raise ApiError(400, "Nie znaleźliśmy wgranego zdjęcia, spróbuj ponownie", fields=["key"])
    current = _account(claims["sub"])
    me = _save_account(claims["sub"], account.with_photo(current, key))
    if current.get("photoKey") != key:
        account.delete_file(current.get("photoKey"))
    return me


def delete_photo(claims: dict) -> dict:
    current = _account(claims["sub"])
    me = _save_account(claims["sub"], account.with_photo(current, None))
    account.delete_file(current.get("photoKey"))
    return me


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
    """Zapis na wydarzenie (kopiuje display_name z tokenu, a bez niego z users; nigdy e-mail ani pełne nazwisko).
    Ponowny zapis nic nie zmienia."""
    if not store.get_event(event_id):
        raise ApiError(404, "Nie znaleziono wydarzenia")
    store.save(event_id, claims["sub"], display_name(claims) or _stored_name(claims["sub"]), now_iso())
    return {"saved": True, "saves": store.saves_of(event_id)}


def delete_save(claims: dict, event_id: str) -> dict:
    """Wypisanie. Działa też dla wydarzeń, które już wygasły; ponowne nic nie zmienia."""
    store.unsave(event_id, claims["sub"])
    return {"saved": False, "saves": store.saves_of(event_id)}


def get_attendees(claims: dict, event_id: str) -> dict:
    """Lista zapisanych: userId i imię (nigdy e-maile), najnowsi najpierw."""
    rows = store.attendees(event_id)
    me = claims["sub"]
    item = store.all_events().get(event_id) if rows else None
    # znajomi widzą tylko nadchodzące zapisy - na minionych wydarzeniach nikt nie jest oznaczony
    mine = friends.friend_ids(me) if item and _upcoming(events.next_slot(item, now=_now())) else {}
    people = [
        {
            "userId": row["userId"],
            "name": row.get("name") or ANONYMOUS,
            "isMe": row["userId"] == me,
            "isFriend": row["userId"] in mine,
        }
        for row in rows
    ]
    people.sort(key=lambda p: 0 if p["isMe"] else 1 if p["isFriend"] else 2)  # stabilnie: w grupie najnowsi
    return {"saves": store.saves_of(event_id), "saved": store.is_saved(event_id, me), "people": people}


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


def get_my_events(claims: dict) -> dict:
    """Zakładka „Twoje”: wydarzenia, na które jestem zapisany (GSI byUser + pamięć codzis-events)."""
    found = events.my_events(store.my_saves(claims["sub"]), store.all_events(), _now(), MY_EVENTS_LIMIT)
    counts = store.saves_for(item["id"] for item, _, _ in found) if found else {}
    return {
        "items": [
            events.card(item, slot, counts[item["id"]], True) | {"past": row["past"], "savedAt": row.get("savedAt")}
            for item, slot, row in found
        ]
    }


def get_friends(claims: dict) -> dict:
    """Moja zakładka Znajomi: kod (pierwszy raz losowany), znajomi i zaproszenia."""
    friends.get_or_create_code(claims["sub"], _require_name(claims))
    return friends.overview(claims["sub"], _epoch())


def post_invite(claims: dict, body: dict) -> dict:
    code = body.get("code")
    if not isinstance(code, str):
        raise ApiError(400, "Podaj kod znajomego", fields=["code"])
    return friends.invite(claims["sub"], _require_name(claims), code, _epoch())


def put_friend_request(claims: dict, from_id: str) -> dict:
    return friends.accept(claims["sub"], _require_name(claims), from_id, _epoch())


def get_friends_going(claims: dict) -> dict:
    """„Znajomi idą”: nadchodzące zapisy znajomych (≤ 50 zapytań GSI byUser) + mapa wydarzenie -> znajomi.

    Znajomi jako {"userId", "name"} (po imieniu, potem po userId) - dwie „Ole” to dwie osoby.
    """
    now = _now()
    going: dict[str, list[dict[str, str]]] = {}
    for friend_id, name in friends.friend_ids(claims["sub"]).items():
        for row in store.my_saves(friend_id):
            going.setdefault(row["eventId"], []).append({"userId": friend_id, "name": name})
    known = store.all_events()
    upcoming = [(known[i], events.next_slot(known[i], now=now)) for i in going if i in known]
    page = [(item, slot) for item, slot in upcoming if slot and _upcoming(slot)]
    page.sort(key=lambda pair: (events.slot_sort_key(pair[1]), events.plain_text(pair[0].get("title"))))
    by_event = {item["id"]: sorted(going[item["id"]], key=_friend_order) for item, _ in page}
    cards = _cards(claims, page[:GOING_LIMIT])
    return {"items": [card | {"friends": by_event[card["id"]]} for card in cards], "byEvent": by_event}


def _friend_order(friend: dict[str, str]) -> tuple[str, str]:
    return (friend["name"].casefold(), friend["userId"])


def _cards(claims: dict, page: list[tuple[dict, dict]]) -> list[dict]:
    """Karty z licznikami z bazy (nie z pamięci) i stanem "Zapisano" użytkownika."""
    counts = store.saves_for(item["id"] for item, _ in page) if page else {}
    mine = store.saved_ids(claims["sub"]) if page else set()
    return [events.card(item, slot, counts[item["id"]], item["id"] in mine) for item, slot in page]


def _window(date_from: date, date_to: date) -> dict:
    return {"from": date_from.isoformat(), "to": date_to.isoformat()}


def display_name(claims: dict) -> str | None:
    """Imię widoczne dla innych z ID tokenu: `name` + inicjał `family_name` („Ola K.”); bez imienia -> None.

    Jedyne miejsce, które składa imię kopiowane do zapisów i znajomych - pełnego nazwiska nie oddajemy nikomu."""
    return _format_name(claims.get("name"), claims.get("family_name"))


def _format_name(first: object, family: object) -> str | None:
    name = _clean_name(first)
    initial = next((c for c in _clean_name(family) or "" if c.isalpha()), None)
    if not name:
        return None
    return f"{name} {initial.upper()}." if initial else name


def _stored_name(user_id: str) -> str | None:
    """Zapas, gdy token nie ma imienia: `displayName` + `familyName` zapisane przez GET /api/me (kopie claimów)."""
    item = users.get_item(Key={"userId": user_id}, ProjectionExpression="displayName, familyName").get("Item") or {}
    return _format_name(item.get("displayName"), item.get("familyName"))


def _upcoming(slot: dict | None) -> bool:
    """Termin od teraz, z datą (zajęcia bez harmonogramu nie mają daty - "nie wiadomo kiedy")."""
    return bool(slot and (slot.get("date") or slot.get("start")))


def _require_name(claims: dict) -> str:
    """Znajomi muszą wiedzieć, kogo dodają: imię z tokenu albo z users, inaczej 409 name_required."""
    name = display_name(claims) or _stored_name(claims["sub"])
    if not name:
        raise ApiError(409, "Podaj imię, zanim dodasz znajomych", code="name_required")
    return name


def _clean_name(value: object) -> str | None:
    name = " ".join(str(value or "").split())[:MAX_NAME]
    return name or None


def _now() -> datetime:
    return datetime.now(events.WARSAW)


def _epoch() -> int:
    """Teraz w sekundach epoki (czasy i TTL w codzis-friends)."""
    return int(_now().timestamp())


def _query(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


# Parametry ścieżki: id wydarzenia (kal-…, spt-…, demo-…) i userId (sub z Cognito, seed-…). Krótki identyfikator
# z liter, cyfr, "-" i "_"; wszystko inne -> 404, zanim trafi jako klucz do DynamoDB.
PATH_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _event_id(event: dict) -> str:
    event_id = (event.get("pathParameters") or {}).get("id") or ""
    if not PATH_ID.fullmatch(event_id):
        raise ApiError(404, "Nie znaleziono wydarzenia")
    return event_id


def _path(event: dict, name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name) or ""
    if not PATH_ID.fullmatch(value):
        raise ApiError(404, "Nie znaleziono")
    return value


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


def _account(user_id: str) -> dict:
    item = users.get_item(
        Key={"userId": user_id}, ProjectionExpression="#account", ExpressionAttributeNames={"#account": "account"}
    ).get("Item")
    return (item or {}).get("account") or {}


def _preferences(answers: dict, birth_date: str | None) -> dict:
    """Preferencje z odpowiedzi ankiety + przedział wieku z daty urodzenia (dzień w Warszawie)."""
    return with_age(compute_preferences(answers, STEPS), birth_date, events.warsaw_today(_now()))


def _save_account(user_id: str, value: dict, preferences: dict | None = None) -> dict:
    """Zapis mapy account; z preferences (nowa data urodzenia) także preferencje i profil RAG."""
    now = now_iso()
    update = "SET #account = :account, updatedAt = :now, createdAt = if_not_exists(createdAt, :now)"
    values: dict = {":account": value, ":now": now}
    if preferences is not None:
        update += ", preferences = :preferences, ragProfile = :rag"
        values |= {":preferences": preferences, ":rag": rag_profile(preferences)}
    item = users.update_item(
        Key={"userId": user_id},
        UpdateExpression=update,
        ExpressionAttributeNames={"#account": "account"},
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )["Attributes"]
    return _view(item)


def _view(item: dict) -> dict:
    onboarding = item.get("onboarding") or {}
    completed = bool(onboarding.get("completedAt"))
    return {
        "userId": item["userId"],
        "email": item.get("email"),
        "name": item.get("displayName"),
        "familyName": item.get("familyName"),
        "picture": item.get("picture"),
        "account": account.view(item.get("account")),
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
