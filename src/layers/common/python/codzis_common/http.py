"""HTTP w Lambdach API: błędy, odczyt body, odpowiedź JSON i obsługa żądania z logiem dostępu.

    raise ApiError(400, "Niepoprawne pola", fields=["title"])  -> {"error": "...", "fields": [...]}
    body = parse_body(event)                                    # obiekt JSON albo ApiError 400
    return response(200, {"items": items})                      # Decimal z DynamoDB -> int/float

    def handler(event, context):                                # punkt wejścia Lambdy
        return handle_request(event, event.get("routeKey"), lambda: route(event))

`handle_request` zamienia ApiError na odpowiedź, a każdy inny wyjątek na 500
{"error": SERVER_ERROR, "requestId"} (pełny traceback w logu). Na każde żądanie jedna linia logu
dostępu w JSON: {"route", "status", "durationMs", "requestId"} - bez body, claims, e-maili, imion
i lokalizacji. requestId = event["requestContext"]["requestId"] z API Gateway: ten sam identyfikator
widzi użytkownik w odpowiedzi 500, więc po nim szukamy w CloudWatch Logs (Logs Insights:
`filter requestId = "..."`).

Nagłówki CORS dodaje API Gateway - nie dopisujemy ich tutaj.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

SERVER_ERROR = "Coś poszło nie tak. Spróbuj ponownie."

# Poziom INFO raz, tutaj: Lambda wysyła wszystko z loggera do CloudWatch Logs.
log = logging.getLogger("codzis.http")
log.setLevel(logging.INFO)


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


def handle_request(event: dict[str, Any], route: str | None, run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Wywołuje trasę `run()` i zawsze zwraca odpowiedź HTTP, z jedną linią logu dostępu.

    ApiError -> jej status i body (4xx: WARNING ze statusem i kodem). Inny wyjątek -> logger.exception
    z trasą i requestId, a klient dostaje 500 {"error": SERVER_ERROR, "requestId"} zamiast pustego 502."""
    request_id = (event.get("requestContext") or {}).get("requestId")
    started = time.monotonic()
    try:
        result = run()
    except ApiError as e:
        level = logging.WARNING if e.status < 500 else logging.ERROR
        log.log(level, _line(route, request_id, status=e.status, code=e.body.get("code")))
        result = response(e.status, e.body)
    except Exception:
        log.exception(_line(route, request_id, error="unhandled"))
        result = response(500, {"error": SERVER_ERROR, "requestId": request_id})
    duration_ms = round((time.monotonic() - started) * 1000)
    log.info(_line(route, request_id, status=result["statusCode"], durationMs=duration_ms))
    return result


def _line(route: str | None, request_id: str | None, **fields: Any) -> str:
    """Jedna linia logu w JSON (tylko trasa, requestId i podane pola - nigdy dane użytkownika)."""
    return json.dumps({"route": route, **fields, "requestId": request_id}, ensure_ascii=False)
