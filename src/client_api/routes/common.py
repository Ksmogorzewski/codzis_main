"""Pomocniki wspólne dla tras API klienta: wejście z żądania, czas i karty z licznikami."""

from datetime import datetime
from typing import Any

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter
from pydantic import TypeAdapter, ValidationError

import events
import store
from codzis_common.app import ApiError
from codzis_common.http import parse_body
from schemas import PathId

NOT_FOUND = "Nie znaleziono"

_path_param = TypeAdapter(PathId)


def claims(router: APIGatewayHttpRouter) -> dict[str, Any]:
    """Claims ID tokenu Cognito (token sprawdziło już API Gateway); claims["sub"] = id użytkownika."""
    return router.current_event.raw_event["requestContext"]["authorizer"]["jwt"]["claims"]


def body(router: APIGatewayHttpRouter) -> dict[str, Any]:
    """Body jako obiekt JSON (brak = {}); zły JSON albo nie-obiekt -> 400."""
    return parse_body(router.current_event.raw_event)


def query(router: APIGatewayHttpRouter) -> dict[str, str]:
    return router.current_event.raw_event.get("queryStringParameters") or {}


def path_id(value: str, message: str = NOT_FOUND) -> str:
    """Parametr ścieżki przez schemas.PathId; zły -> 404 `message`, zanim trafi jako klucz do DynamoDB."""
    try:
        return _path_param.validate_python(value)
    except ValidationError:
        raise ApiError(404, message) from None


def now() -> datetime:
    """Teraz w Warszawie - jedyne źródło czasu tras (testy podmieniają `routes.common.now`)."""
    return datetime.now(events.WARSAW)


def epoch() -> int:
    """Teraz w sekundach epoki (czasy i TTL w codzis-friends)."""
    return int(now().timestamp())


def upcoming(slot: dict | None) -> bool:
    """Termin od teraz, z datą (zajęcia bez harmonogramu nie mają daty - "nie wiadomo kiedy")."""
    return bool(slot and (slot.get("date") or slot.get("start")))


def cards(user: dict, page: list[tuple[dict, dict]]) -> list[dict]:
    """Karty z licznikami z bazy (nie z pamięci) i stanem "Zapisano" użytkownika."""
    counts = store.saves_for(item["id"] for item, _ in page) if page else {}
    mine = store.saved_ids(user["sub"]) if page else set()
    return [events.card(item, slot, counts[item["id"]], item["id"] in mine) for item, slot in page]
