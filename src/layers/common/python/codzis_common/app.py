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
- Wejście klienta walidujemy tylko na granicy: `parse_input(Model, data, "komunikat")` -> 400
  `{"error": "komunikat", "fields": [...]}` (albo własne `ApiError` z `validation_fields(e)`).
- `pydantic.ValidationError` niezłapany w trasie = błąd po naszej stronie (np. dane z bazy) -> 500; w logu tylko
  model, typy i miejsca błędów - nigdy `str(e)` ani `e.errors()` (zawierają wartości wejścia).
- Każdy inny wyjątek (także błąd serializacji odpowiedzi) -> `logger.exception` (pełny traceback) i
  `500 {"error": SERVER_ERROR, "requestId"}` (`requestId: null`, gdy API Gateway go nie podało).
- Nieznana trasa i zła metoda -> `404 {"error": "Nie znaleziono"}` (zamiast 404 Powertools).
- Body: `json.dumps(ensure_ascii=False, default=json_default)` - polskie znaki bez escapowania, `Decimal` z DynamoDB
  -> int/float; jedyny nagłówek `Content-Type: application/json` (także w REST API v1: `headers`, nie
  `multiValueHeaders`). CORS dodaje API Gateway - Powertools nie dostaje `cors`.

Logi (Powertools `Logger`, JSON w CloudWatch, `correlation_id` = requestId API Gateway - ten sam, który klient
widzi w odpowiedzi 500; Logs Insights: `filter correlation_id = "..."`): jedna linia `"message": "access"` na
żądanie z `route` (szablon trasy, np. "GET /api/events/{id}" - bez identyfikatorów z adresu; nieznana trasa:
"GET (unmatched)"), `status`, `durationMs`. Nigdy body, claims, e-maili, imion, lokalizacji, tokenów. Serwis:
`POWERTOOLS_SERVICE_NAME`.
"""

import json
import time
import traceback
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


def validation_fields(error: ValidationError, sort: bool = False) -> list[str]:
    """Nazwy błędnych pól najwyższego poziomu (bez powtórzeń) - dla `fields`.

    Kolejność błędów Pydantic, a z `sort=True` alfabetycznie (jak dziś ogłoszenia partnera i ankieta)."""
    fields: list[str] = []
    for item in error.errors():
        loc = item["loc"]
        if loc and isinstance(loc[0], str) and loc[0] not in fields:
            fields.append(loc[0])
    return sorted(fields) if sort else fields


def parse_input[M: BaseModel](model: type[M], data: object, message: str = INVALID_INPUT) -> M:
    """Wejście (body/query/ścieżka) przez model; błąd -> ApiError 400 {"error": message, "fields": [...]}."""
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ApiError(400, message, fields=validation_fields(e)) from None


def current_request_id(app: ApiGatewayResolver) -> str | None:
    """requestId API Gateway bieżącego żądania (= correlation_id w logach); None, gdy go brak."""
    return _request_id(app.current_event.raw_event)


def _request_id(event: Mapping[str, Any]) -> str | None:
    request_id = (event.get("requestContext") or {}).get("requestId")
    return str(request_id) if request_id else None


def _stack(error: BaseException) -> list[str]:
    """Ślad stosu jako "plik:linia w funkcji" - bez komunikatu wyjątku i tekstu kodu (mogą zawierać dane)."""
    return [f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in traceback.extract_tb(error.__traceback__)]


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
        self.exception_handler(ValidationError)(self._server_validation_error)
        self.exception_handler(Exception)(self._unexpected_error)
        self.not_found(self._not_found)

    def resolve(self, event: Mapping[str, Any], context: LambdaContext) -> dict[str, Any]:
        """Obsługa żądania + jedna linia logu dostępu (route, status, durationMs; correlation_id = requestId)."""
        started = time.monotonic()
        self._access_route = None
        logger.set_correlation_id(_request_id(event))
        try:
            result = _single_value_headers(super().resolve(event, context))
        except Exception as error:
            # Powertools serializuje body już po swojej obsłudze wyjątków (np. set albo datetime w odpowiedzi):
            # bez tego API Gateway oddałby pusty 502, a w logu nie byłoby linii dostępu.
            self.clear_context()
            logger.error(
                "unhandled", extra={"route": self._access_route, "error": type(error).__name__, "stack": _stack(error)}
            )
            result = self._fallback_error(event)
        duration_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "access", extra={"route": self._access_route, "status": result["statusCode"], "durationMs": duration_ms}
        )
        return result

    def _remember_route(self, app: ApiGatewayResolver, next_middleware: NextMiddleware) -> Response:
        """Middleware: zapamiętuje szablon dopasowanej trasy ("GET /api/events/{id}"; nieznaną ustawia `_not_found`)."""
        self._access_route = f"{app.request.method} {app.request.route}"
        return next_middleware(app)

    @staticmethod
    def _fallback_error(event: Mapping[str, Any]) -> dict[str, Any]:
        """Odpowiedź 500 zbudowana poza Powertools - ten sam kształt i serializacja co reszta."""
        body = to_json({"error": SERVER_ERROR, "requestId": _request_id(event)})
        return {"statusCode": 500, "body": body, "isBase64Encoded": False, "headers": {"Content-Type": JSON}}

    def _api_error(self, error: ApiError) -> Response:
        extra = {"route": self._access_route, "status": error.status, "code": error.body.get("code")}
        if error.status < 500:
            logger.warning("api_error", extra=extra)
        else:
            logger.error("api_error", extra=extra)
        return Response(status_code=error.status, content_type=JSON, body=error.body)

    def _server_validation_error(self, error: ValidationError) -> Response:
        """ValidationError poza `parse_input` = nasze dane nie pasują do modelu -> 500, log bez wartości."""
        problems = [{"loc": list(item["loc"]), "type": item["type"]} for item in error.errors(include_input=False)]
        extra = {"route": self._access_route, "model": error.title, "problems": problems, "stack": _stack(error)}
        logger.error("invalid_data", extra=extra)
        return self._server_error()

    def _unexpected_error(self, error: Exception) -> Response:
        logger.exception("unhandled", extra={"route": self._access_route})
        return self._server_error()

    def _server_error(self) -> Response:
        body = {"error": SERVER_ERROR, "requestId": current_request_id(self)}
        return Response(status_code=500, content_type=JSON, body=body)

    def _not_found(self, _: NotFoundError) -> Response:
        # Bez surowej ścieżki: nieznany adres może zawierać identyfikatory.
        self._access_route = f"{self.current_event.http_method} (unmatched)"
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
