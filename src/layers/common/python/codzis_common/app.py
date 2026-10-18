"""Aplikacja HTTP Lambd API na AWS Lambda Powertools: router, logger, błędy i linia dostępu w jednym miejscu.

    # handler.py - tylko złożenie aplikacji
    from aws_lambda_powertools.event_handler import APIGatewayHttpResolver   # REST API v1: APIGatewayRestResolver
    from codzis_common.app import create_app
    from routes import events, me

    app = create_app(APIGatewayHttpResolver)
    app.include_router(me.router)
    app.include_router(events.router)

    def handler(event, context):
        return app.resolve(event, context)

    # routes/me.py - trasy jednej domeny
    from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter
    from codzis_common.app import ApiError, parse_input
    from codzis_common.http import parse_body          # JSON-obiekt albo 400 (jak dotąd)
    from schemas import PutMe

    router = APIGatewayHttpRouter()

    @router.put("/api/me")
    def put_me() -> dict:
        body = parse_input(PutMe, parse_body(router.current_event.raw_event), "Niepoprawne dane profilu")
        return {...}                    # dict -> 200 JSON; (dict, 201) -> inny status

Kontrakt HTTP jak w dawnym `codzis_common.http.handle_request` + `response`:
- `ApiError(status, message, **extra)` -> status i body `{"error": message, **extra}` (4xx: WARNING ze statusem
  i `code`, 5xx: ERROR).
- `pydantic.ValidationError` niezłapany w trasie -> `400 {"error": "Niepoprawne dane", "fields": [...]}`;
  własny komunikat trasy: `parse_input(Model, data, "komunikat")` albo `validation_fields(e)`.
- Każdy inny wyjątek -> `logger.exception` (pełny traceback) i `500 {"error": SERVER_ERROR, "requestId"}`.
- Nieznana trasa i zła metoda -> `404 {"error": "Nie znaleziono"}` (zamiast 404 Powertools).
- Body: `json.dumps(ensure_ascii=False, default=json_default)` - polskie znaki bez escapowania, `Decimal` z DynamoDB
  -> int/float; jedyny nagłówek `Content-Type: application/json` (także w REST API v1: `headers`, nie
  `multiValueHeaders`). CORS dodaje API Gateway - Powertools nie dostaje `cors`.

Logi (Powertools `Logger`, JSON w CloudWatch, `correlation_id` = requestId API Gateway - ten sam, który klient
widzi w odpowiedzi 500; Logs Insights: `filter correlation_id = "..."`): jedna linia `"message": "access"` na
żądanie z `route` (szablon trasy, np. "GET /api/events/{id}" - bez identyfikatorów z adresu), `status`,
`durationMs`. Nigdy body, claims, e-maili, imion, lokalizacji, tokenów. Serwis: `POWERTOOLS_SERVICE_NAME`.
"""

import json
import re
import time
from collections.abc import Mapping
from functools import partial
from typing import Any, overload

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import ApiGatewayResolver
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from aws_lambda_powertools.event_handler.middlewares import NextMiddleware
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel, ValidationError

from codzis_common.http import SERVER_ERROR, ApiError, json_default

__all__ = [
    "SERVER_ERROR",
    "ApiError",
    "create_app",
    "current_request_id",
    "logger",
    "parse_input",
    "to_json",
    "validation_fields",
]

NOT_FOUND = "Nie znaleziono"
INVALID_INPUT = "Niepoprawne dane"
JSON = "application/json"

logger = Logger()


def _json_value(value: object) -> object:
    """`default=` serializera: Decimal -> int/float (jak `json_default`), model Pydantic -> dict."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    return json_default(value)


# Dokładnie jak dawne response(): domyślne separatory, polskie znaki bez escapowania.
to_json = partial(json.dumps, ensure_ascii=False, default=_json_value)


def validation_fields(error: ValidationError) -> list[str]:
    """Nazwy błędnych pól najwyższego poziomu (bez powtórzeń, w kolejności błędów Pydantic) - dla `fields`."""
    fields: list[str] = []
    for item in error.errors():
        loc = item["loc"]
        if loc and isinstance(loc[0], str) and loc[0] not in fields:
            fields.append(loc[0])
    return fields


def parse_input[M: BaseModel](model: type[M], data: object, message: str = INVALID_INPUT) -> M:
    """Wejście (body/query/ścieżka) przez model; błąd -> ApiError 400 {"error": message, "fields": [...]}."""
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ApiError(400, message, fields=validation_fields(e)) from None


def current_request_id(app: ApiGatewayResolver) -> str:
    """requestId API Gateway bieżącego żądania (= correlation_id w logach); "" gdy go brak."""
    return _request_id(app.current_event.raw_event)


def _request_id(event: Mapping[str, Any]) -> str:
    return str((event.get("requestContext") or {}).get("requestId") or "")


def _route_template(method: str, path: str) -> str:
    """Szablon trasy do logu: reguła Powertools "/api/events/<id>" -> "GET /api/events/{id}" (jak routeKey)."""
    return f"{method} {re.sub(r'<(\w+)>', r'{\1}', path)}"


def _single_value_headers(result: dict[str, Any]) -> dict[str, Any]:
    """REST API v1: Powertools zwraca `multiValueHeaders`; zwracamy `headers` jak dawne response()."""
    multi = result.pop("multiValueHeaders", None)
    if multi is not None:
        result["headers"] = {key: ", ".join(values) for key, values in multi.items()}
    return result


class _App(ApiGatewayResolver):
    """Wspólne zachowanie obu API. Nie twórz bezpośrednio - użyj `create_app`."""

    def __init__(self) -> None:
        # debug=False: POWERTOOLS_DEV nie może wypisać całych zdarzeń (z body i tokenami) do logów.
        super().__init__(serializer=to_json, debug=False)
        self._access_route: str | None = None
        self.use([self._remember_route])
        self.exception_handler(ApiError)(self._api_error)
        self.exception_handler(ValidationError)(self._validation_error)
        self.exception_handler(Exception)(self._unexpected_error)
        self.not_found(self._not_found)

    def resolve(self, event: Mapping[str, Any], context: LambdaContext) -> dict[str, Any]:
        """Obsługa żądania + jedna linia logu dostępu (route, status, durationMs; correlation_id = requestId)."""
        started = time.monotonic()
        self._access_route = None
        logger.set_correlation_id(_request_id(event) or None)
        result = _single_value_headers(super().resolve(event, context))
        duration_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "access", extra={"route": self._access_route, "status": result["statusCode"], "durationMs": duration_ms}
        )
        return result

    def _remember_route(self, app: ApiGatewayResolver, next_middleware: NextMiddleware) -> Response:
        """Middleware: zapamiętuje szablon dopasowanej trasy (dla nieznanej trasy - ścieżkę) do logów."""
        route = app.context.get("_route")
        if route is not None:
            self._access_route = _route_template(route.method, route.path)
        return next_middleware(app)

    def _api_error(self, error: ApiError) -> Response:
        extra = {"route": self._access_route, "status": error.status, "code": error.body.get("code")}
        if error.status < 500:
            logger.warning("api_error", extra=extra)
        else:
            logger.error("api_error", extra=extra)
        return Response(status_code=error.status, content_type=JSON, body=error.body)

    def _validation_error(self, error: ValidationError) -> Response:
        return self._api_error(ApiError(400, INVALID_INPUT, fields=validation_fields(error)))

    def _unexpected_error(self, error: Exception) -> Response:
        logger.exception("unhandled", extra={"route": self._access_route})
        body = {"error": SERVER_ERROR, "requestId": current_request_id(self)}
        return Response(status_code=500, content_type=JSON, body=body)

    def _not_found(self, _: NotFoundError) -> Response:
        return self._api_error(ApiError(404, NOT_FOUND))


class _HttpApp(_App, APIGatewayHttpResolver):
    """client-api: HTTP API (payload 2.0)."""


class _RestApp(_App, APIGatewayRestResolver):
    """API partnera: REST API v1 z proxy /{proxy+}."""


@overload
def create_app(resolver_cls: type[APIGatewayHttpResolver]) -> APIGatewayHttpResolver: ...
@overload
def create_app(resolver_cls: type[APIGatewayRestResolver]) -> APIGatewayRestResolver: ...
def create_app(resolver_cls: type[ApiGatewayResolver]) -> ApiGatewayResolver:
    """Aplikacja Powertools z naszym formatem błędów, 404, serializacją JSON i linią dostępu.

    `resolver_cls`: `APIGatewayHttpResolver` (client-api, HTTP API v2) albo `APIGatewayRestResolver`
    (API partnera, REST API v1). Trasy dokładamy przez `app.include_router(router)`."""
    if issubclass(resolver_cls, APIGatewayHttpResolver):
        return _HttpApp()
    if issubclass(resolver_cls, APIGatewayRestResolver):
        return _RestApp()
    raise TypeError(f"Nieobsługiwany resolver: {resolver_cls.__name__}")
