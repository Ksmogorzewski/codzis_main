"""HTTP w Lambdach API: błędy, odczyt body i odpowiedź JSON.

    raise ApiError(400, "Niepoprawne pola", fields=["title"])  -> {"error": "...", "fields": [...]}
    body = parse_body(event)                                    # obiekt JSON albo ApiError 400
    return response(200, {"items": items})                      # Decimal z DynamoDB -> int/float

Nagłówki CORS dodaje API Gateway - nie dopisujemy ich tutaj.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


class ApiError(Exception):
    """Błąd zwracany klientowi: status HTTP + body {"error": message, **extra}."""

    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.body = {"error": message, **extra}


def parse_body(event: dict[str, Any], parse_float: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Body żądania jako obiekt JSON (brak body = {}). Błędny JSON albo nie-obiekt -> ApiError 400.

    parse_float=Decimal zachowuje dokładność liczb (np. cen) do zapisu w DynamoDB."""
    try:
        body = json.loads(event.get("body") or "{}", parse_float=parse_float)
    except json.JSONDecodeError:
        raise ApiError(400, "Niepoprawny JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "Oczekiwano obiektu JSON")
    return body


def json_default(value: object) -> int | float:
    """`default=` dla json.dumps: Decimal (liczby z DynamoDB) -> int albo float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Nie da się zserializować {type(value).__name__}")


def response(status: int, body: Any) -> dict[str, Any]:
    """Odpowiedź Lambda proxy (API Gateway REST i HTTP API) z body w JSON (polskie znaki bez escapowania)."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, default=json_default),
    }


def now_iso() -> str:
    """Bieżący czas UTC w ISO 8601 z offsetem, np. 2026-10-17T10:00:00.123456+00:00."""
    return datetime.now(UTC).isoformat()
