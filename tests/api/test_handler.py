"""Handler API panelu partnera (src/api/handler.py) na atrapach DynamoDB i SQS."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.api.conftest import PARTNER_KEY, PARTNER_NAME, STARTER_CREDITS, call
from tests.support import taxonomy

WARSAW = "+02:00"


def future(days=7, hour=19):
    day = datetime.now(UTC) + timedelta(days=days)
    return f"{day:%Y-%m-%d}T{hour:02d}:00:00{WARSAW}"


def valid_event(**overrides):
    body = {
        "title": "  Koncert w parku ",
        "lead": "Muzyka na żywo",
        "text": "Pierwszy akapit\nz nową linią\n\nDrugi <b>akapit</b>",
        "venue": "Park Skaryszewski",
        "street": "al. Zieleniecka",
        "streetNumber": "1",
        "url": "https://example.com/koncert",
        "cost": "Płatne",
        "registration": "Wymagany bilet",
        "setting": "Na zewnątrz",
        "audience": ["Rodziny / wszystkie grupy", "Dorośli (18-64)", "Dorośli (18-64)"],
        "priceMin": "20",
        "priceMax": 35.5,
        "category": "Kultura",
        "district": "Wola",
        "startsAt": future(hour=19),
        "endsAt": future(hour=21),
        "photoContentType": "image/jpeg",
    }
    body.update(overrides)
    return body


def post_event(partner_api, **overrides):
    return call(partner_api, "POST", "events", valid_event(**overrides))


def fields_error(partner_api, **overrides):
    status, body = post_event(partner_api, **overrides)
    assert status == 400, body
    assert body["error"] == "Niepoprawne lub brakujące pola"
    return body["fields"]


# --- GET /me ---


def test_get_me_creates_partner_with_starter_credits(partner_api, aws):
    status, body = call(partner_api, "GET", "me")

    assert status == 200
    assert body["partnerId"] == PARTNER_KEY
    assert body["partnerName"] == PARTNER_NAME
    assert body["credits"] == STARTER_CREDITS
    assert body["eventCost"] == 1
    assert set(body["formOptions"]) == {"cost", "registration", "setting", "audience", "accessibility"}
    assert aws.credits() == STARTER_CREDITS


def test_get_me_keeps_existing_credits(partner_api, aws):
    aws.partners.put_item(Item={"partnerId": PARTNER_KEY, "partnerName": "Stara nazwa", "credits": 7})
    _, body = call(partner_api, "GET", "me")
    assert body["credits"] == 7
    assert aws.partners.get_item(Key={"partnerId": PARTNER_KEY})["Item"]["partnerName"] == PARTNER_NAME


def test_get_me_unknown_key_uses_key_id_as_name(partner_api):
    _, body = call(partner_api, "GET", "me", api_key="key-unknown")
    assert body["partnerName"] == "key-unknown"


# --- logowanie Google (samoobsługa: konto Google = konto organizatora) ---

GOOGLE = {"sub": "5f1c2e7a-google", "name": "  Anna   Nowak ", "email": "anna@example.com", "email_verified": "true"}


def test_google_first_login_creates_partner_from_token(partner_api, aws):
    status, body = call(partner_api, "GET", "me", claims=GOOGLE)

    assert status == 200
    assert body["partnerId"] == GOOGLE["sub"]
    assert body["partnerName"] == "Anna Nowak"
    assert body["credits"] == STARTER_CREDITS
    assert "email" not in body
    assert aws.partners.get_item(Key={"partnerId": GOOGLE["sub"]})["Item"] == {
        "partnerId": GOOGLE["sub"],
        "partnerName": "Anna Nowak",
        "credits": STARTER_CREDITS,
    }


def test_google_account_without_name_gets_default_name(partner_api):
    _, body = call(partner_api, "GET", "me", claims={"sub": "bez-imienia"})
    assert body["partnerName"] == "Organizator"


def test_google_partner_signs_events_with_google_name_only(partner_api, aws):
    call(partner_api, "GET", "me", claims=GOOGLE)

    status, body = call(partner_api, "POST", "events", valid_event(), claims=GOOGLE)

    assert status == 201
    assert aws.credits(GOOGLE["sub"]) == STARTER_CREDITS - 1
    (record,) = aws.messages()[0]
    assert (record["partnerId"], record["partnerName"]) == (GOOGLE["sub"], "Anna Nowak")
    assert "anna@example.com" not in str(record)  # e-mail z Google nie trafia do publicznego rekordu
    _, own = call(partner_api, "GET", "events", claims=GOOGLE)
    assert [i["id"] for i in own["items"]] == [body["id"]]
    _, key_partner = call(partner_api, "GET", "events")
    assert key_partner["items"] == []


def test_form_options_are_taxonomy_values(partner_api):
    _, body = call(partner_api, "GET", "me")
    options = taxonomy()
    for name, values in body["formOptions"].items():
        assert set(values) <= set(options[name]), name


# --- POST /events: walidacja ---


def test_create_event_missing_required_fields(partner_api):
    status, body = call(partner_api, "POST", "events", {})
    assert status == 400
    assert body == {
        "error": "Niepoprawne lub brakujące pola",
        "fields": [
            "category",
            "cost",
            "district",
            "lead",
            "registration",
            "setting",
            "startsAt",
            "title",
            "venue",
        ],
    }


def test_create_event_blank_strings_count_as_missing(partner_api):
    assert fields_error(partner_api, title="   ", venue="") == ["title", "venue"]


def test_create_event_text_rules(partner_api):
    assert fields_error(partner_api, title="x" * 201) == ["title"]
    assert fields_error(partner_api, lead=123) == ["lead"]
    assert fields_error(partner_api, url="ftp://example.com", ticketUrl="example.com") == ["ticketUrl", "url"]


@pytest.mark.parametrize(
    ("overrides", "fields"),
    [
        ({"cost": "Za darmo"}, ["cost"]),
        ({"cost": None, "priceMin": None, "priceMax": None}, ["cost"]),
        ({"registration": "Nieznane"}, ["registration"]),
        ({"setting": ["Na zewnątrz"]}, ["setting"]),
        ({"audience": "Dorośli (18-64)"}, ["audience"]),
        ({"audience": ["Dorośli (18-64)", "Koty"]}, ["audience"]),
        ({"accessibility": ["Audiodeskrypcja", "Teleportacja"]}, ["accessibility"]),
        ({"category": "Polityka"}, ["category"]),
        ({"district": "Kraków"}, ["district"]),
    ],
)
def test_create_event_declared_and_dictionary_fields(partner_api, overrides, fields):
    assert fields_error(partner_api, **overrides) == fields


@pytest.mark.parametrize(
    ("overrides", "fields"),
    [
        ({"cost": "Bezpłatne"}, ["priceMin"]),  # cena przy wydarzeniu bezpłatnym
        ({"cost": "Bezpłatne", "priceMin": None}, ["priceMax"]),
        ({"priceMin": "50", "priceMax": "10"}, ["priceMax"]),
        ({"priceMin": -1}, ["priceMin"]),
        ({"priceMin": "abc"}, ["priceMin"]),
        ({"priceMax": "NaN"}, ["priceMax"]),
        ({"priceMax": 100_000.01}, ["priceMax"]),
    ],
)
def test_create_event_price_rules(partner_api, overrides, fields):
    assert fields_error(partner_api, **overrides) == fields


@pytest.mark.parametrize(
    ("overrides", "fields"),
    [
        ({"startsAt": "2027-01-29T19:00:00"}, ["startsAt"]),  # bez strefy
        ({"startsAt": "jutro"}, ["startsAt"]),
        ({"endsAt": "nie data"}, ["endsAt"]),
        ({"endsAt": future(hour=18)}, ["endsAt"]),  # przed startem
        ({"startsAt": "2020-01-01T10:00:00+01:00", "endsAt": None}, ["startsAt"]),  # w przeszłości
        ({"startsAt": "2020-01-01T10:00:00+01:00", "endsAt": "2020-01-01T12:00:00+01:00"}, ["endsAt"]),
    ],
)
def test_create_event_date_rules(partner_api, overrides, fields):
    assert fields_error(partner_api, **overrides) == fields


def test_create_event_unsupported_photo_type(partner_api, aws):
    call(partner_api, "GET", "me")
    status, body = post_event(partner_api, photoContentType="image/gif")
    assert status == 400
    assert body == {"error": "Nieobsługiwany typ zdjęcia", "allowed": ["image/jpeg", "image/png", "image/webp"]}
    assert aws.credits() == STARTER_CREDITS


# --- POST /events: zapis ---


def test_create_event_deducts_one_credit_and_queues_record(partner_api, aws):
    call(partner_api, "GET", "me")

    status, body = post_event(partner_api)

    assert status == 201
    event_id = body["id"]
    assert body["upload"]["fields"]["key"] == f"photos/{event_id}/photo.jpg"
    assert body["upload"]["fields"]["Content-Type"] == "image/jpeg"
    assert "test-photos" in body["upload"]["url"]
    assert aws.credits() == STARTER_CREDITS - 1

    submission = aws.submissions.get_item(Key={"id": event_id})["Item"]
    assert submission["status"] == "queued"
    assert submission["partnerId"] == PARTNER_KEY

    messages = aws.messages()
    assert len(messages) == 1
    (record,) = messages[0]
    assert record["id"] == event_id
    assert record["source"] == record["origin"] == "partner"
    assert record["schemaVersion"] == 1
    assert record["kind"] == "event"
    assert record["title"] == "Koncert w parku"
    assert record["text"] == "<p>Pierwszy akapit<br>z nową linią</p>\n<p>Drugi &lt;b&gt;akapit&lt;/b&gt;</p>"
    assert record["category"] == [{"id": None, "name": "Kultura"}]
    assert record["audience"] == ["Dorośli (18-64)", "Rodziny / wszystkie grupy"]
    assert record["venue"] == {"name": "Park Skaryszewski", "address": "al. Zieleniecka 1"}
    assert record["location"] is None
    assert record["imageUrl"] == f"https://partner.example.com/photos/{event_id}/photo.jpg"
    assert record["attributes"] == {"price": {"min": 20, "max": 35.5, "currency": "PLN"}, "ticketUrl": None}
    assert record["declared"] == {
        "cost": "Płatne",
        "registration": "Wymagany bilet",
        "setting": "Na zewnątrz",
        "audience": ["Dorośli (18-64)", "Rodziny / wszystkie grupy"],
    }
    assert record["occurrences"][0]["start"] == valid_event()["startsAt"]
    assert record["startsAt"].endswith("T17:00:00Z")  # 19:00 +02:00 -> UTC
    assert record["endsAt"].endswith("T19:00:00Z")
    assert record["partnerName"] == PARTNER_NAME
    # zapis w tabeli = to samo co w kolejce (+ status), ceny jako Decimal
    assert submission["attributes"]["price"]["max"] == Decimal("35.50")


def test_create_event_free_without_optional_fields(partner_api, aws):
    call(partner_api, "GET", "me")
    status, _ = post_event(
        partner_api,
        cost="Bezpłatne",
        priceMin="",
        priceMax=None,
        text=None,
        street=None,
        streetNumber=None,
        url=None,
        audience=None,
        endsAt=None,
    )
    assert status == 201
    (record,) = aws.messages()[0]
    assert record["text"] == ""
    assert record["venue"]["address"] is None
    assert record["attributes"]["price"] is None
    assert record["audience"] == []
    assert record["occurrences"][0]["end"] is None
    assert record["endsAt"] == record["startsAt"]


def test_create_event_without_credits_returns_402(partner_api, aws):
    call(partner_api, "GET", "me")
    for _ in range(STARTER_CREDITS):
        assert post_event(partner_api)[0] == 201

    status, body = post_event(partner_api)

    assert status == 402
    assert body == {"error": "Brak kredytów", "required": 1}
    assert aws.credits() == 0
    assert len(aws.submissions.scan()["Items"]) == STARTER_CREDITS


def test_create_event_for_partner_without_record_returns_402(partner_api, aws):
    status, _ = post_event(partner_api)
    assert status == 402
    assert aws.submissions.scan()["Items"] == []
    assert aws.messages() == []


def test_create_event_queue_failure_refunds_credit(partner_api, aws):
    call(partner_api, "GET", "me")
    aws.sqs.delete_queue(QueueUrl=aws.queue_url)

    status, body = post_event(partner_api)

    assert status == 503
    assert body == {"error": "Nie udało się przyjąć ogłoszenia, spróbuj ponownie"}
    assert aws.credits() == STARTER_CREDITS
    assert aws.submissions.scan()["Items"] == []


def test_list_events_only_own(partner_api, aws):
    call(partner_api, "GET", "me")
    _, first = post_event(partner_api, title="Pierwsze")
    _, second = post_event(partner_api, title="Drugie")
    aws.submissions.put_item(Item={"id": "obce", "partnerId": "key-2", "createdAt": "2030-01-01"})

    status, body = call(partner_api, "GET", "events")

    assert status == 200
    assert [i["id"] for i in body["items"]] == [second["id"], first["id"]]  # najnowsze najpierw


# --- płatności ---


def test_create_payment_unknown_package(partner_api):
    status, body = call(partner_api, "POST", "payments", {"package": "mega"})
    assert status == 400
    assert body == {"error": "Nieznany pakiet", "allowed": ["starter", "standard"]}


def test_payment_confirm_adds_credits_once(partner_api, aws):
    call(partner_api, "GET", "me")
    status, payment = call(partner_api, "POST", "payments", {"package": "standard"})

    assert status == 201
    assert payment["status"] == "pending"
    assert payment["credits"] == 5
    assert payment["amount"] == 79.99
    assert payment["currency"] == "PLN"
    assert payment["redirectUrl"] == f"/mock-pay.html?id={payment['id']}"
    assert aws.payments.get_item(Key={"id": payment["id"]})["Item"]["amount"] == Decimal("79.99")

    status, confirmed = call(partner_api, "POST", f"payments/{payment['id']}/confirm")
    assert status == 200
    assert confirmed["status"] == "paid"
    assert confirmed["paidAt"]
    assert aws.credits() == STARTER_CREDITS + 5

    status, body = call(partner_api, "POST", f"payments/{payment['id']}/confirm")
    assert status == 409
    assert body == {"error": "Płatność została już rozliczona"}
    assert aws.credits() == STARTER_CREDITS + 5

    _, fetched = call(partner_api, "GET", f"payments/{payment['id']}")
    assert fetched["status"] == "paid"


def test_payment_cancel_pending(partner_api, aws):
    call(partner_api, "GET", "me")
    _, payment = call(partner_api, "POST", "payments", {"package": "starter"})

    status, cancelled = call(partner_api, "POST", f"payments/{payment['id']}/cancel")
    assert status == 200
    assert cancelled["status"] == "cancelled"
    assert cancelled["amount"] == 19

    assert call(partner_api, "POST", f"payments/{payment['id']}/confirm")[0] == 409
    assert call(partner_api, "POST", f"payments/{payment['id']}/cancel")[0] == 409
    assert aws.credits() == STARTER_CREDITS


def test_payment_of_other_partner_is_not_found(partner_api):
    _, payment = call(partner_api, "POST", "payments", {"package": "starter"})
    for method, path in (
        ("GET", f"payments/{payment['id']}"),
        ("POST", f"payments/{payment['id']}/confirm"),
        ("POST", f"payments/{payment['id']}/cancel"),
        ("GET", "payments/brak"),
    ):
        status, body = call(partner_api, method, path, api_key="key-2" if "brak" not in path else PARTNER_KEY)
        assert status == 404
        assert body == {"error": "Nie znaleziono płatności"}


def test_list_payments(partner_api):
    _, first = call(partner_api, "POST", "payments", {"package": "starter"})
    _, second = call(partner_api, "POST", "payments", {"package": "standard"})
    call(partner_api, "POST", "payments", {"package": "starter"}, api_key="key-2")

    status, body = call(partner_api, "GET", "payments")

    assert status == 200
    assert [i["id"] for i in body["items"]] == [second["id"], first["id"]]


# --- routing ---


@pytest.mark.parametrize(
    ("method", "path"),
    [("DELETE", "me"), ("GET", "nic"), ("GET", ""), ("POST", "payments/x/refund"), ("PUT", "events")],
)
def test_unknown_route_404(partner_api, method, path):
    status, body = call(partner_api, method, path)
    assert status == 404
    assert body == {"error": "Nie znaleziono"}


def test_path_with_slashes_is_normalized(partner_api):
    assert call(partner_api, "GET", "/me/")[0] == 200


@pytest.mark.parametrize(
    ("raw", "error"),
    [("{zły json", "Niepoprawny JSON"), ('"tekst"', "Oczekiwano obiektu JSON")],
)
def test_bad_body(partner_api, raw, error):
    status, body = call(partner_api, "POST", "payments", raw)
    assert status == 400
    assert body == {"error": error}
