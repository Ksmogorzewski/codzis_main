"""API portalu klienta (HTTP API + JWT authorizer Cognito, payload 2.0).

    GET /api/me          profil zalogowanego użytkownika (pierwsze wywołanie zakłada rekord)
    GET /api/onboarding  pytania onboardingu (onboarding.py)
    PUT /api/profile     {"answers": {...}} -> walidacja, preferencje, zapis w tabeli users

Token weryfikuje API Gateway; tu korzystamy już tylko z jego claims (ID token Cognito).
Po zapisaniu profilu i przy logowaniu rekomender w tle liczy zestawy na dziś, jutro i weekend
(GET /api/recommendations obsługuje osobna Lambda: src/recommender_api).
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from onboarding import build_steps, compute_preferences, onboarding_version, public_steps, rag_profile, validate_answers

USERS_TABLE = os.environ["USERS_TABLE"]
DISTRICTS = json.loads(os.environ["DISTRICTS"])
RECOMMENDER_FUNCTION = os.environ.get("RECOMMENDER_FUNCTION")

STEPS = build_steps(DISTRICTS)
ONBOARDING_VERSION = onboarding_version(STEPS)

users = boto3.resource("dynamodb").Table(USERS_TABLE)
lambda_client = boto3.client("lambda")

log = logging.getLogger()
log.setLevel(logging.INFO)


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.body = {"error": message, **extra}


def handler(event, context):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    try:
        match event.get("routeKey"):
            case "GET /api/me":
                return _response(200, get_me(claims))
            case "GET /api/onboarding":
                return _response(200, {"version": ONBOARDING_VERSION, "steps": public_steps(STEPS)})
            case "PUT /api/profile":
                return _response(200, put_profile(claims, _body(event)))
        raise ApiError(404, "Nie znaleziono")
    except ApiError as e:
        return _response(e.status, e.body)


def get_me(claims: dict) -> dict:
    """Upsert danych z tokenu (e-mail, imię, dostawca) + ostatnie logowanie."""
    now = _now()
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
    now = _now()
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


def _precompute(user_id: str) -> None:
    """Asynchroniczne wywołanie rekomendera; odpowiedź nie czeka na liczenie."""
    if not RECOMMENDER_FUNCTION:
        return
    try:
        lambda_client.invoke(FunctionName=RECOMMENDER_FUNCTION, InvocationType="Event",
                             Payload=json.dumps({"action": "precompute", "userId": user_id}))
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
        } if completed else None,
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


def _body(event: dict) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise ApiError(400, "Niepoprawny JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "Oczekiwano obiektu JSON")
    return body


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value):
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Nie da się zserializować {type(value).__name__}")


def _response(status: int, body) -> dict:
    # Nagłówki CORS dodaje HTTP API (cors_configuration w infra/client_api.tf)
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, default=_json_default),
    }
