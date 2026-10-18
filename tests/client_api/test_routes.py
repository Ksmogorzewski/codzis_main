"""Kontrakt HTTP API klienta: błędy walidacji (komunikat + `fields` w tej kolejności).

Oczekiwane odpowiedzi to zachowanie sprzed przejścia na router Powertools i modele Pydantic - nie mogą się zmienić.
"""

import pytest

from tests.client_api.conftest import call

VALID_ANSWERS = {
    "who": "kids",
    "vibe": ["active"],
    "discover": ["history", "guided"],
    "district": "Wola",
    "travel": "local",
    "budget": "up50",
}
NAMED = {"sub": "user-1", "name": "Ala"}

FILTERS = "Niepoprawne filtry"
DAY = "Podaj dzień od dziś do 60 dni naprzód (RRRR-MM-DD)"
ANSWERS = "Niepoprawne lub brakujące odpowiedzi"
CODE = "Podaj kod znajomego"
IDS = "Podaj od 1 do 100 identyfikatorów"
ME = "Niepoprawne dane profilu"
PHOTO_TYPE = "Zdjęcie musi być w formacie JPG, PNG albo WebP"
PHOTO_KEY = "Nie znaleźliśmy wgranego zdjęcia, spróbuj ponownie"


def _error(message, *fields):
    return {"error": message, "fields": list(fields)}


VALIDATION_CASES = [
    # GET /api/events: pola w kolejności sprawdzania (when, date, cat, district, limit), bez sortowania
    ("GET /api/events", {"query": {"when": "kiedyś"}}, _error(FILTERS, "when")),
    (
        "GET /api/events",
        {"query": {"when": "kiedyś", "cat": "x", "district": "Nigdzie", "limit": "dużo"}},
        _error(FILTERS, "when", "cat", "district", "limit"),
    ),
    ("GET /api/events", {"query": {"when": "date"}}, _error(DAY, "date")),
    ("GET /api/events", {"query": {"when": "date", "date": ""}}, _error(DAY, "date")),
    ("GET /api/events", {"query": {"when": "date", "date": "2026-13-01", "cat": "x"}}, _error(FILTERS, "date", "cat")),
    ("GET /api/events", {"query": {"limit": "1.5"}}, _error(FILTERS, "limit")),
    # GET /api/events/stats
    ("GET /api/events/stats", {}, _error(IDS, "ids")),
    ("GET /api/events/stats", {"query": {"ids": ""}}, _error(IDS, "ids")),
    ("GET /api/events/stats", {"query": {"ids": " , ,"}}, _error(IDS, "ids")),
    ("GET /api/events/stats", {"query": {"ids": ",".join(f"e{n}" for n in range(101))}}, _error(IDS, "ids")),
    # PUT /api/profile: pola posortowane
    ("PUT /api/profile", {"body": {}}, _error(ANSWERS, "answers")),
    ("PUT /api/profile", {"body": {"answers": None}}, _error(ANSWERS, "answers")),
    ("PUT /api/profile", {"body": {"answers": "kids"}}, _error(ANSWERS, "answers")),
    ("PUT /api/profile", {"body": {"answers": ["kids"]}}, _error(ANSWERS, "answers")),
    ("PUT /api/profile", {"body": {"answers": {**VALID_ANSWERS, "who": 5}}}, _error(ANSWERS, "who")),
    ("PUT /api/profile", {"body": {"answers": {**VALID_ANSWERS, "who": ""}}}, _error(ANSWERS, "who")),
    ("PUT /api/profile", {"body": {"answers": {**VALID_ANSWERS, "zbędne": "x"}}}, _error(ANSWERS, "zbędne")),
    (
        "PUT /api/profile",
        {"body": {"answers": {**VALID_ANSWERS, "who": "aliens", "vibe": [], "budget": ["up50", 1]}}},
        _error(ANSWERS, "budget", "vibe", "who"),
    ),
    # POST /api/friends/invite: zły kod -> 400 jeszcze przed sprawdzeniem imienia (409)
    ("POST /api/friends/invite", {"body": {}}, _error(CODE, "code")),
    ("POST /api/friends/invite", {"body": {"code": None}}, _error(CODE, "code")),
    ("POST /api/friends/invite", {"body": {"code": 5}}, _error(CODE, "code")),
    ("POST /api/friends/invite", {"body": {"code": ["WAW-7K2P9X"], "zbędne": 1}}, _error(CODE, "code")),
    (
        "POST /api/friends/invite",
        {"body": {"code": ""}},
        {"error": "Podaj imię, zanim dodasz znajomych", "code": "name_required"},
    ),
    # PUT /api/me
    ("PUT /api/me", {"body": {"birthDate": 5}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": True}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": ["2000-01-01"]}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": "2026-13-01"}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": "1899-12-31"}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": "2999-01-01"}}, _error(ME, "birthDate")),
    ("PUT /api/me", {"body": {"birthDate": "18.10.2000"}}, _error(ME, "birthDate")),
    # zdjęcie profilowe
    ("POST /api/me/photo", {"body": {}}, _error(PHOTO_TYPE, "contentType")),
    ("POST /api/me/photo", {"body": {"contentType": 5}}, _error(PHOTO_TYPE, "contentType")),
    ("POST /api/me/photo", {"body": {"contentType": "image/gif"}}, _error(PHOTO_TYPE, "contentType")),
    ("PUT /api/me/photo", {"body": {}}, _error(PHOTO_KEY, "key")),
    ("PUT /api/me/photo", {"body": {"key": 5}}, _error(PHOTO_KEY, "key")),
    ("PUT /api/me/photo", {"body": {"key": "photos/avatars/user-2/0123456789abcdef.jpg"}}, _error(PHOTO_KEY, "key")),
]


@pytest.mark.parametrize(("route", "request_parts", "expected"), VALIDATION_CASES)
def test_validation_errors_unchanged(client_api, route, request_parts, expected):
    status, body = call(client_api, route, **request_parts)
    assert (status, body) == (409 if "code" in expected else 400, expected)


@pytest.mark.parametrize(
    ("route", "request_parts"),
    [
        ("GET /api/events", {"query": {"when": "", "nieznany": "1"}}),  # pusty when = dziś, nadmiarowe pomijamy
        ("GET /api/events/stats", {"query": {"ids": "a", "nieznany": "1"}}),
        ("PUT /api/me", {"body": {"birthDate": "", "familyName": "Nowak"}}),  # pusta data = usuń
        ("PUT /api/me", {"body": {}}),
        ("PUT /api/profile", {"body": {"answers": VALID_ANSWERS, "zbędne": 1}}),
        ("POST /api/me/photo", {"body": {"contentType": "image/png", "zbędne": 1}}),
    ],
)
def test_valid_input_with_extra_fields_accepted(client_api, route, request_parts):
    assert call(client_api, route, claims=NAMED, **request_parts)[0] == 200
