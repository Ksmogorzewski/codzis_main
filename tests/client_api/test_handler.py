"""Handler API klienta (src/client_api/handler.py) na atrapie DynamoDB."""

import json
from decimal import Decimal

import pytest

from tests.client_api.conftest import api_event, call

VALID_ANSWERS = {
    "who": "kids",
    "vibe": ["active"],
    "discover": ["history", "guided"],
    "district": "Wola",
    "travel": "local",
    "budget": "up50",
}


# --- GET /api/me ---


def test_get_me_creates_user_from_claims(client_api, users_table):
    claims = {"sub": "user-1", "email": "ala@example.com", "name": "Ala"}
    status, body = call(client_api, "GET /api/me", claims=claims)

    assert status == 200
    assert body == {
        "userId": "user-1",
        "email": "ala@example.com",
        "name": "Ala",
        "picture": None,
        "identityProvider": "Cognito",
        "needsOnboarding": True,
        "onboardingOutdated": False,
        "profile": None,
    }
    item = users_table.get_item(Key={"userId": "user-1"})["Item"]
    assert item["createdAt"] == item["lastLoginAt"]
    assert item["displayName"] == "Ala"
    assert "picture" not in item


def test_get_me_keeps_created_at_on_second_call(client_api, users_table):
    call(client_api, "GET /api/me")
    first = users_table.get_item(Key={"userId": "user-1"})["Item"]

    status, _ = call(client_api, "GET /api/me", claims={"sub": "user-1", "email": "nowy@example.com"})
    second = users_table.get_item(Key={"userId": "user-1"})["Item"]

    assert status == 200
    assert second["createdAt"] == first["createdAt"]
    assert second["lastLoginAt"] >= first["lastLoginAt"]
    assert second["email"] == "nowy@example.com"


def test_get_me_federated_provider(client_api):
    identities = json.dumps([{"providerName": "Google", "userId": "123"}])
    _, body = call(client_api, "GET /api/me", claims={"sub": "user-2", "identities": identities})
    assert body["identityProvider"] == "Google"


def test_get_me_bad_identities_claim_falls_back_to_cognito(client_api):
    _, body = call(client_api, "GET /api/me", claims={"sub": "user-3", "identities": "nie-json"})
    assert body["identityProvider"] == "Cognito"


# --- GET /api/onboarding ---


def test_get_onboarding_shape(client_api):
    status, body = call(client_api, "GET /api/onboarding")

    assert status == 200
    assert set(body) == {"version", "steps"}
    assert body["version"] == client_api.ONBOARDING_VERSION
    assert len(body["version"]) == 12
    assert [s["id"] for s in body["steps"]][:4] == ["who", "vibe", "discover", "city"]
    option = body["steps"][0]["fields"][0]["options"][0]
    assert set(option) == {"id", "label", "icon", "short"}


# --- PUT /api/profile ---


def test_put_profile_saves_and_returns_view(client_api, users_table):
    status, body = call(client_api, "PUT /api/profile", {"answers": VALID_ANSWERS})

    assert status == 200
    assert body["needsOnboarding"] is False
    assert body["onboardingOutdated"] is False
    profile = body["profile"]
    assert profile["answers"] == {k: v if isinstance(v, list) else [v] for k, v in VALID_ANSWERS.items()}
    assert profile["preferences"]["district"] == "Wola"
    assert profile["preferences"]["maxPrice"] == 50  # Decimal z DynamoDB -> int w JSON
    assert profile["ragProfile"].startswith("interests=[")
    assert profile["completedAt"]

    item = users_table.get_item(Key={"userId": "user-1"})["Item"]
    assert item["onboarding"]["version"] == client_api.ONBOARDING_VERSION
    assert item["preferences"]["maxPrice"] == Decimal(50)
    assert item["createdAt"] == item["updatedAt"]

    # Kolejne GET /api/me widzi zapisany profil
    _, me = call(client_api, "GET /api/me")
    assert me["profile"] == profile


def test_put_profile_invalid_answers(client_api, users_table):
    status, body = call(client_api, "PUT /api/profile", {"answers": {**VALID_ANSWERS, "who": "aliens", "vibe": []}})

    assert status == 400
    assert body == {"error": "Niepoprawne lub brakujące odpowiedzi", "fields": ["vibe", "who"]}
    assert "Item" not in users_table.get_item(Key={"userId": "user-1"})


def test_put_profile_missing_answers(client_api):
    status, body = call(client_api, "PUT /api/profile", {})
    assert status == 400
    assert body["fields"] == ["answers"]


@pytest.mark.parametrize(
    ("raw", "error"),
    [("{nie json", "Niepoprawny JSON"), ("[1, 2]", "Oczekiwano obiektu JSON")],
)
def test_put_profile_bad_body(client_api, raw, error):
    status, body = call(client_api, "PUT /api/profile", raw)
    assert status == 400
    assert body == {"error": error}


def test_onboarding_outdated_when_version_changed(client_api, users_table):
    call(client_api, "PUT /api/profile", {"answers": VALID_ANSWERS})
    users_table.update_item(
        Key={"userId": "user-1"},
        UpdateExpression="SET onboarding.version = :v",
        ExpressionAttributeValues={":v": "stara-wersja"},
    )
    _, body = call(client_api, "GET /api/me")
    assert body["needsOnboarding"] is False
    assert body["onboardingOutdated"] is True


# --- rekomender w tle ---


class FakeLambda:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def invoke(self, **kwargs):
        if self.fail:
            raise RuntimeError("niedostępne")
        self.calls.append(kwargs)


def test_put_profile_triggers_precompute(client_api, monkeypatch):
    fake = FakeLambda()
    monkeypatch.setattr(client_api, "RECOMMENDER_FUNCTION", "recommender")
    monkeypatch.setattr(client_api, "lambda_client", fake)

    call(client_api, "PUT /api/profile", {"answers": VALID_ANSWERS})
    call(client_api, "GET /api/me")  # z preferencjami -> też zleca przeliczenie

    assert [c["InvocationType"] for c in fake.calls] == ["Event", "Event"]
    assert json.loads(fake.calls[0]["Payload"]) == {"action": "precompute", "userId": "user-1"}


def test_get_me_without_preferences_does_not_precompute(client_api, monkeypatch):
    fake = FakeLambda()
    monkeypatch.setattr(client_api, "RECOMMENDER_FUNCTION", "recommender")
    monkeypatch.setattr(client_api, "lambda_client", fake)
    call(client_api, "GET /api/me")
    assert fake.calls == []


def test_precompute_failure_does_not_fail_request(client_api, monkeypatch):
    monkeypatch.setattr(client_api, "RECOMMENDER_FUNCTION", "recommender")
    monkeypatch.setattr(client_api, "lambda_client", FakeLambda(fail=True))
    status, _ = call(client_api, "PUT /api/profile", {"answers": VALID_ANSWERS})
    assert status == 200


# --- routing i serializacja ---


def test_unknown_route_404(client_api):
    status, body = call(client_api, "DELETE /api/me")
    assert status == 404
    assert body == {"error": "Nie znaleziono"}


def test_response_keeps_polish_characters(client_api):
    response = client_api.handler(api_event("PUT /api/profile", "[]"), None)
    assert "Oczekiwano obiektu JSON" in response["body"]  # ensure_ascii=False
    response = client_api.handler(api_event("GET /api/onboarding"), None)
    assert "Śródmieście" in response["body"]


def test_decimal_from_dynamodb_serialized_as_int_or_float(client_api, users_table):
    users_table.put_item(
        Item={
            "userId": "user-1",
            "onboarding": {"completedAt": "2026-10-17T10:00:00+00:00", "version": "x", "answers": {}},
            "preferences": {"maxPrice": Decimal("12.5"), "count": Decimal("3")},
        }
    )
    _, body = call(client_api, "GET /api/me")
    assert body["profile"]["preferences"] == {"maxPrice": 12.5, "count": 3}
