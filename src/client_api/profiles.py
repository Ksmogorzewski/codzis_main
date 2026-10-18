"""Użytkownicy (tabela codzis-users, jedyny zapisujący: client-api): rekord z tokenu, ankieta, dane konta, imię.

Rekord: userId (= sub z Cognito), kopie claimów (email, displayName = imię, familyName = nazwisko, picture),
identityProvider, createdAt/lastLoginAt/updatedAt, onboarding {version, completedAt, answers}, preferences,
ragProfile, account (account.py). Widok dla właściciela: `view`.

Imię widoczne dla innych (zapisy, zaproszenia, znajomi, podgląd kodu) składa tylko `display_name`: imię + inicjał
nazwiska („Ola K.”); pełnego nazwiska nie oddajemy nikomu.

Preferencje = odpowiedzi ankiety + przedział wieku z daty urodzenia (account.birthDate, onboarding.with_age),
więc liczą się przy zapisie ankiety i przy zmianie daty urodzenia (`update_account`).

Po zapisaniu profilu i przy logowaniu `precompute` zleca rekomenderowi (osobna Lambda) zestawy na dziś, jutro
i weekend - asynchronicznie, odpowiedź na to nie czeka.
"""

import json
import os
from datetime import date

import boto3

import account
from codzis_common.app import ApiError, logger
from codzis_common.aws import AWS_CONFIG
from codzis_common.http import now_iso
from onboarding import (
    build_steps,
    compute_preferences,
    missing_required,
    onboarding_version,
    rag_profile,
    with_age,
)

USERS_TABLE = os.environ["USERS_TABLE"]
DISTRICTS = json.loads(os.environ["DISTRICTS"])
RECOMMENDER_FUNCTION = os.environ.get("RECOMMENDER_FUNCTION")
MAX_NAME = 60

STEPS = build_steps(DISTRICTS)
ONBOARDING_VERSION = onboarding_version(STEPS)

users = boto3.resource("dynamodb", config=AWS_CONFIG).Table(USERS_TABLE)
lambda_client = boto3.client("lambda", config=AWS_CONFIG)


def login(claims: dict) -> dict:
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
        precompute(claims["sub"])  # liczy tylko brakujące lub nieaktualne zestawy
    return view(item)


def save_answers(user_id: str, answers: dict, today: date) -> dict:
    """Zapis sprawdzonych odpowiedzi ankiety (onboarding.validate_answers) + preferencje (z wiekiem z daty
    urodzenia w danych konta; today = dzień w Warszawie) -> widok profilu."""
    preferences = preferences_for(answers, account_of(user_id).get("birthDate"), today)
    now = now_iso()
    item = users.update_item(
        Key={"userId": user_id},
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
    precompute(user_id)  # nowe preferencje -> od razu nowe zestawy na dziś, jutro i weekend
    return view(item)


def account_of(user_id: str) -> dict:
    """Mapa account użytkownika (pusta, gdy brak)."""
    item = users.get_item(
        Key={"userId": user_id}, ProjectionExpression="#account", ExpressionAttributeNames={"#account": "account"}
    ).get("Item")
    return (item or {}).get("account") or {}


def update_account(user_id: str, values: dict, today: date) -> dict:
    """Sprawdzone dane konta (account.validate) -> widok profilu. Z daty urodzenia liczymy przedział wieku
    w preferencjach, więc przy wypełnionej ankiecie przeliczamy też preferencje i profil RAG; inny wynik ->
    nowe zestawy rekomendacji."""
    user = (
        users.get_item(
            Key={"userId": user_id},
            ProjectionExpression="#account, onboarding, preferences",
            ExpressionAttributeNames={"#account": "account"},
        ).get("Item")
        or {}
    )
    value = account.merge(user.get("account") or {}, values)
    onboarding = user.get("onboarding") or {}
    preferences = None
    if onboarding.get("completedAt"):
        preferences = preferences_for(onboarding.get("answers") or {}, value.get("birthDate"), today)
    me = save_account(user_id, value, preferences)
    if preferences is not None and preferences != user.get("preferences"):
        precompute(user_id)  # inny przedział wieku -> nowe zestawy rekomendacji
    return me


def save_account(user_id: str, value: dict, preferences: dict | None = None) -> dict:
    """Nowa mapa account -> widok profilu; z preferences (nowa data urodzenia) także preferencje i profil RAG."""
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
    return view(item)


def preferences_for(answers: dict, birth_date: str | None, today: date) -> dict:
    """Preferencje z odpowiedzi ankiety + przedział wieku z daty urodzenia (today = dzień w Warszawie)."""
    return with_age(compute_preferences(answers, STEPS), birth_date, today)


def view(item: dict) -> dict:
    """Profil dla właściciela (odpowiedź tras /api/me i PUT /api/profile)."""
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
        # doszło wymagane pytanie bez odpowiedzi - front prosi o uzupełnienie (bez wymuszania ankiety);
        # usunięte pytania, nowe etykiety/mapowania i nowe pola opcjonalne profilu nie dezaktualizują
        "onboardingOutdated": completed and bool(missing_required(onboarding.get("answers") or {}, STEPS)),
        "profile": {
            "answers": onboarding.get("answers", {}),
            "completedAt": onboarding.get("completedAt"),
            "preferences": item.get("preferences"),
            "ragProfile": item.get("ragProfile"),
        }
        if completed
        else None,
    }


def display_name(claims: dict) -> str | None:
    """Imię widoczne dla innych z ID tokenu: `name` + inicjał `family_name` („Ola K.”); bez imienia -> None.

    Jedyne miejsce, które składa imię kopiowane do zapisów i znajomych - pełnego nazwiska nie oddajemy nikomu."""
    return _format_name(claims.get("name"), claims.get("family_name"))


def stored_name(user_id: str) -> str | None:
    """Zapas, gdy token nie ma imienia: `displayName` + `familyName` zapisane przez GET /api/me (kopie claimów)."""
    item = users.get_item(Key={"userId": user_id}, ProjectionExpression="displayName, familyName").get("Item") or {}
    return _format_name(item.get("displayName"), item.get("familyName"))


def require_name(claims: dict) -> str:
    """Znajomi muszą wiedzieć, kogo dodają: imię z tokenu albo z users, inaczej 409 name_required."""
    name = display_name(claims) or stored_name(claims["sub"])
    if not name:
        raise ApiError(409, "Podaj imię, zanim dodasz znajomych", code="name_required")
    return name


def precompute(user_id: str) -> None:
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
        logger.exception("Nie udało się zlecić przeliczenia rekomendacji")


def _format_name(first: object, family: object) -> str | None:
    name = _clean_name(first)
    initial = next((c for c in _clean_name(family) or "" if c.isalpha()), None)
    if not name:
        return None
    return f"{name} {initial.upper()}." if initial else name


def _clean_name(value: object) -> str | None:
    name = " ".join(str(value or "").split())[:MAX_NAME]
    return name or None


def _provider(claims: dict) -> str:
    # Użytkownicy federacyjni mają claim "identities" (JSON jako tekst), np. [{"providerName": "Google", ...}]
    try:
        identities = json.loads(claims.get("identities") or "[]")
        if identities:
            return identities[0].get("providerName") or "Federated"
    except (TypeError, ValueError):
        pass
    return "Cognito"
