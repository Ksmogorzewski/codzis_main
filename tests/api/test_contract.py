"""Kontrakt HTTP API partnera po przejściu na router Powertools: walidacja (te same `fields`), trasy, logi."""

import copy
import json

import pytest

from tests.api.conftest import PARTNER_KEY, PARTNER_NAME, REQUEST_ID, call, rest_event
from tests.api.test_handler import GOOGLE, future, valid_event

FIELDS_ERROR = "Niepoprawne lub brakujące pola"
PACKAGES_ERROR = {"error": "Nieznany pakiet", "allowed": ["starter", "standard"]}
PAST = "2020-01-01T10:00:00+01:00"


def invoke(module, event):
    response = module.handler(event, None)
    assert response["headers"] == {"Content-Type": "application/json"}
    return response["statusCode"], json.loads(response["body"])


# --- POST /events: błędy pól i błędy między polami zbierane razem, posortowane ---


@pytest.mark.parametrize(
    ("overrides", "fields"),
    [
        ({"title": None, "priceMin": "50", "priceMax": "10"}, ["priceMax", "title"]),
        ({"startsAt": "jutro", "cost": "Bezpłatne"}, ["priceMin", "startsAt"]),
        ({"venue": "x" * 201, "endsAt": future(hour=18)}, ["endsAt", "venue"]),
        ({"priceMin": "abc", "cost": "Bezpłatne"}, ["priceMax", "priceMin"]),  # zła cena liczy się jak brak ceny
        ({"cost": "Za darmo", "priceMin": "50", "priceMax": "10"}, ["cost"]),  # bez kosztu nie ma reguł ceny
        ({"endsAt": "nie data", "startsAt": PAST}, ["endsAt", "startsAt"]),
        ({"endsAt": PAST, "startsAt": "2019-01-01T10:00:00+01:00", "lead": " "}, ["endsAt", "lead"]),
        ({"title": "x" * 199 + "  "}, ["title"]),  # długość liczona przed obcięciem spacji
        ({"category": ["Kultura"], "district": None}, ["category", "district"]),
        ({"audience": [["Dorośli (18-64)"]], "accessibility": "Audiodeskrypcja"}, ["accessibility", "audience"]),
        ({"startsAt": 1_900_000_000, "priceMin": True}, ["priceMin", "startsAt"]),
        (
            {"registration": "", "setting": {"x": 1}, "streetNumber": "1" * 21},
            ["registration", "setting", "streetNumber"],
        ),
        (
            {"text": 5, "street": ["ul."], "url": "https://ok.pl", "ticketUrl": "www.bilety.pl"},
            ["street", "text", "ticketUrl"],
        ),
    ],
)
def test_create_event_reports_every_bad_field_sorted(partner_api, overrides, fields):
    status, body = call(partner_api, "POST", "events", valid_event(**overrides))
    assert status == 400
    assert body == {"error": FIELDS_ERROR, "fields": fields}


def test_create_event_field_errors_before_photo_type(partner_api):
    status, body = call(partner_api, "POST", "events", valid_event(title="", photoContentType="image/gif"))
    assert (status, body) == (400, {"error": FIELDS_ERROR, "fields": ["title"]})


@pytest.mark.parametrize("photo", [None, "", "IMAGE/JPEG", ["image/jpeg"]])
def test_create_event_bad_photo_type(partner_api, photo):
    call(partner_api, "GET", "me")
    status, body = call(partner_api, "POST", "events", valid_event(photoContentType=photo))
    assert status == 400
    assert body == {"error": "Nieobsługiwany typ zdjęcia", "allowed": ["image/jpeg", "image/png", "image/webp"]}


def test_create_event_ignores_unknown_fields_and_falsy_end(partner_api, aws):
    call(partner_api, "GET", "me")
    status, _ = call(partner_api, "POST", "events", valid_event(endsAt="", isAdmin=True, credits=1000))
    assert status == 201
    (record,) = aws.messages()[0]
    assert record["occurrences"][0]["end"] is None
    assert "isAdmin" not in record


# --- POST /payments: zły pakiet -> 400 z listą pakietów ---


@pytest.mark.parametrize("body", [{}, {"package": None}, {"package": ""}, {"package": 1}, {"package": "mega"}])
def test_create_payment_bad_package(partner_api, body):
    assert call(partner_api, "POST", "payments", body) == (400, PACKAGES_ERROR)


def test_create_payment_package_as_list_is_400_not_500(partner_api):
    # Przed refaktorem: TypeError (lista jako klucz słownika) -> 500.
    assert call(partner_api, "POST", "payments", {"package": ["starter"]}) == (400, PACKAGES_ERROR)


# --- routing: trasa z pathParameters.proxy, oba sposoby logowania ---


def test_routes_on_proxy_even_if_path_has_base_path(partner_api):
    # Za własną domeną z mapowaniem ścieżki API Gateway dokleja prefiks do `path`; trasę wyznacza proxy.
    event = rest_event("GET", "me")
    event["path"] = "/api/me"
    original = copy.deepcopy(event)

    status, body = invoke(partner_api, event)

    assert (status, body["partnerId"], body["partnerName"]) == (200, PARTNER_KEY, PARTNER_NAME)
    assert event == original  # handler nie zmienia zdarzenia


def test_routes_with_google_token_claims(partner_api):
    event = rest_event("GET", "me", claims=GOOGLE)
    assert event["requestContext"]["identity"]["apiKeyId"] is None

    status, body = invoke(partner_api, event)

    assert (status, body["partnerId"], body["partnerName"]) == (200, GOOGLE["sub"], "Anna Nowak")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "api/me"),  # prefiks stage'a nie jest częścią trasy
        ("GET", "payments/x/confirm"),
        ("PUT", "payments/x"),
        ("POST", "payments/x/confirm/extra"),
        ("GET", "me/x"),
        ("PATCH", "events"),
        ("OPTIONS", "me"),  # CORS robi API Gateway / ta sama domena - Lambda nie odpowiada na preflight
        ("HEAD", "me"),
    ],
)
def test_unknown_route_or_method_404(partner_api, method, path):
    assert call(partner_api, method, path) == (404, {"error": "Nie znaleziono"})


# --- log dostępu: szablon trasy bez identyfikatorów, correlation_id = requestId ---


def test_access_log_hides_payment_id(partner_api, access_logs):
    call(partner_api, "GET", "me")
    _, payment = call(partner_api, "POST", "payments", {"package": "starter"})
    payment_id = payment["id"]
    call(partner_api, "GET", f"payments/{payment_id}")
    call(partner_api, "POST", f"payments/{payment_id}/confirm")
    call(partner_api, "POST", f"payments/{payment_id}/cancel")

    lines = access_logs()
    access = [(line["route"], line["status"]) for line in lines if line["message"] == "access"]
    assert access == [
        ("GET /me", 200),
        ("POST /payments", 201),
        ("GET /payments/{id}", 200),
        ("POST /payments/{id}/confirm", 200),
        ("POST /payments/{id}/cancel", 409),
    ]
    assert all(line["correlation_id"] == REQUEST_ID for line in lines)
    assert payment_id not in json.dumps(lines)


def test_logs_never_contain_body_or_claims(partner_api, access_logs):
    call(partner_api, "POST", "events", valid_event(title="Tajny tytuł"), claims=GOOGLE)
    logged = json.dumps(access_logs(), ensure_ascii=False)
    assert "Tajny tytuł" not in logged
    assert GOOGLE["email"] not in logged
    assert GOOGLE["sub"] not in logged
