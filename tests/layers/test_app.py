"""Wspólna aplikacja Powertools: src/layers/common/python/codzis_common/app.py.

Sprawdzamy kontrakt HTTP obu API (client-api: HTTP API v2, partner: REST API v1) - kształt błędów, 404,
nagłówki, serializację - oraz linię dostępu w logu (JSON z Powertools Logger, bez body)."""

import io
import json
from decimal import Decimal

import pytest
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, APIGatewayRestResolver
from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import BaseModel, ValidationError

from codzis_common.app import (
    SERVER_ERROR,
    ApiError,
    create_app,
    current_request_id,
    logger,
    parse_input,
    validation_fields,
)
from codzis_common.http import parse_body

REQUEST_ID = "req-1"
SECRET_BODY = '{"email": "ala@example.com"}'
CONTEXT = LambdaContext()


class Invite(BaseModel):
    code: str
    count: int


def _routes(app):
    @app.get("/api/ok")
    def ok():
        return {"name": "Śródmieście", "price": Decimal("12.50"), "n": Decimal(1)}

    @app.post("/api/created")
    def created():
        return {"id": "x"}, 201

    @app.get("/api/items/<item_id>")
    def item(item_id: str):
        return {"id": item_id}

    @app.get("/api/conflict")
    def conflict():
        raise ApiError(409, "Podaj imię", code="name_required")

    @app.get("/api/unavailable")
    def unavailable():
        raise ApiError(503, "Usługa niedostępna")

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("awaria")

    @app.post("/api/invite")
    def invite():
        # ValidationError poza parse_input = nasze dane (np. z bazy) nie pasują do modelu
        Invite.model_validate({"count": "tajne-dane-z-bazy"})
        return {}

    @app.post("/api/input")
    def input_():
        body = parse_input(Invite, parse_body(app.current_event.raw_event), "Podaj kod znajomego")
        return {"code": body.code}

    @app.get("/api/unserializable")
    def unserializable():
        return {"a": {1}}

    @app.get("/api/request-id")
    def request_id():
        return {"requestId": current_request_id(app)}

    return app


def http_event(method, path, body=None):
    """Zdarzenie HTTP API v2 (client-api), jak wysyła API Gateway."""
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {"http": {"method": method, "path": path}, "requestId": REQUEST_ID, "stage": "$default"},
        "body": body,
        "isBase64Encoded": False,
    }


def rest_event(method, path, body=None):
    """Zdarzenie REST API v1 z proxy /{proxy+} (API partnera)."""
    return {
        "resource": "/{proxy+}",
        "path": path,
        "httpMethod": method,
        "headers": {"Content-Type": "application/json"},
        "pathParameters": {"proxy": path.strip("/")},
        "requestContext": {"requestId": REQUEST_ID, "stage": "prod", "path": f"/prod{path}"},
        "body": body,
        "isBase64Encoded": False,
    }


APPS = [(APIGatewayHttpResolver, http_event), (APIGatewayRestResolver, rest_event)]


@pytest.fixture(params=APPS, ids=["http-v2", "rest-v1"])
def call(request):
    resolver_cls, make_event = request.param
    app = _routes(create_app(resolver_cls))

    def _call(method, path, body=None):
        return app.resolve(make_event(method, path, body), CONTEXT)

    return _call


@pytest.fixture
def log_lines():
    """Linie logu (JSON) z Powertools Logger - podmieniamy strumień jego handlera."""
    stream = io.StringIO()
    previous = logger.registered_handler.setStream(stream)  # type: ignore[attr-defined]
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    logger.registered_handler.setStream(previous)  # type: ignore[attr-defined]


def _body(result):
    return json.loads(result["body"])


def test_ok_status_and_body(call):
    result = call("POST", "/api/created")
    assert result["statusCode"] == 201
    assert _body(result) == {"id": "x"}


def test_api_error_shape(call):
    result = call("GET", "/api/conflict")
    assert result["statusCode"] == 409
    assert _body(result) == {"error": "Podaj imię", "code": "name_required"}


def test_unexpected_error_500_with_request_id(call, log_lines):
    result = call("GET", "/api/boom")
    assert result["statusCode"] == 500
    assert _body(result) == {"error": SERVER_ERROR, "requestId": REQUEST_ID}
    [error] = [line for line in log_lines() if line["level"] == "ERROR"]
    assert error["route"] == "GET /api/boom"
    assert error["correlation_id"] == REQUEST_ID
    assert "RuntimeError" in error["exception"]  # pełny traceback w CloudWatch


@pytest.mark.parametrize(("method", "path"), [("GET", "/api/nie-ma"), ("PUT", "/api/ok"), ("DELETE", "/")])
def test_not_found_shape(call, method, path):
    """Nieznana trasa i zła metoda -> nasz 404 (Powertools domyślnie zwraca własny)."""
    result = call(method, path)
    assert result["statusCode"] == 404
    assert _body(result) == {"error": "Nie znaleziono"}
    assert result["headers"] == {"Content-Type": "application/json"}


@pytest.mark.parametrize("path", ["/api/ok", "/api/conflict", "/api/boom", "/api/nie-ma"])
def test_response_headers_unchanged(call, path):
    """Tylko Content-Type: application/json, jak w dzisiejszym response(); CORS dodaje API Gateway."""
    result = call("GET", path)
    assert result["headers"] == {"Content-Type": "application/json"}
    assert "multiValueHeaders" not in result
    assert not result.get("cookies")
    assert result.get("isBase64Encoded") in (None, False)


def test_decimal_and_polish_serialization(call):
    result = call("GET", "/api/ok")
    assert result["statusCode"] == 200
    # dokładnie jak dzisiejsze response(): ensure_ascii=False, Decimal -> int/float, domyślne separatory
    assert result["body"] == json.dumps({"name": "Śródmieście", "price": 12.5, "n": 1}, ensure_ascii=False)


def test_client_input_validation_is_400_with_fields(call):
    result = call("POST", "/api/input", '{"count": "x"}')
    assert result["statusCode"] == 400
    assert _body(result) == {"error": "Podaj kod znajomego", "fields": ["code", "count"]}


def test_server_side_validation_error_is_500_without_values(call, log_lines):
    result = call("POST", "/api/invite")
    assert result["statusCode"] == 500
    assert _body(result) == {"error": SERVER_ERROR, "requestId": REQUEST_ID}
    lines = log_lines()
    [error] = [line for line in lines if line["level"] == "ERROR"]
    assert (error["message"], error["route"], error["model"]) == ("invalid_data", "POST /api/invite", "Invite")
    assert {"loc": ["count"], "type": "int_parsing"} in error["problems"]
    assert "tajne-dane-z-bazy" not in json.dumps(lines)
    assert [line["status"] for line in lines if line["message"] == "access"] == [500]


def test_unserializable_response_is_500_with_access_line(call, log_lines):
    result = call("GET", "/api/unserializable")
    assert result["statusCode"] == 500
    assert result["headers"] == {"Content-Type": "application/json"}
    assert result["body"] == json.dumps({"error": SERVER_ERROR, "requestId": REQUEST_ID}, ensure_ascii=False)
    lines = log_lines()
    [error] = [line for line in lines if line["level"] == "ERROR"]
    assert (error["message"], error["route"], error["error"]) == ("unhandled", "GET /api/unserializable", "TypeError")
    [access] = [line for line in lines if line["message"] == "access"]
    assert (access["route"], access["status"]) == ("GET /api/unserializable", 500)
    # następne żądanie w tym samym kontenerze działa normalnie (kontekst wyczyszczony)
    assert _body(call("GET", "/api/items/x")) == {"id": "x"}


def test_missing_request_id_is_null():
    app = _routes(create_app(APIGatewayHttpResolver))
    event = http_event("GET", "/api/boom")
    del event["requestContext"]["requestId"]
    result = app.resolve(event, CONTEXT)
    assert _body(result) == {"error": SERVER_ERROR, "requestId": None}


def test_current_request_id(call):
    assert _body(call("GET", "/api/request-id")) == {"requestId": REQUEST_ID}


def test_access_log_line(call, log_lines):
    call("GET", "/api/items/abc-123")
    [access] = [line for line in log_lines() if line["message"] == "access"]
    assert access["route"] == "GET /api/items/{item_id}"  # szablon trasy, bez identyfikatora z adresu
    assert access["status"] == 200
    assert isinstance(access["durationMs"], int)
    assert access["correlation_id"] == REQUEST_ID
    assert access["level"] == "INFO"
    assert "abc-123" not in json.dumps(access)


def test_access_log_on_errors(call, log_lines):
    for path in ("/api/conflict", "/api/unavailable", "/api/boom", "/api/nie-ma"):
        call("GET", path)
    lines = log_lines()
    statuses = [line["status"] for line in lines if line["message"] == "access"]
    assert statuses == [409, 503, 500, 404]
    warning = next(line for line in lines if line["level"] == "WARNING")
    assert (warning["route"], warning["status"], warning["code"]) == ("GET /api/conflict", 409, "name_required")
    assert any(line["level"] == "ERROR" and line.get("status") == 503 for line in lines)


def test_unmatched_route_logged_without_path(call, log_lines):
    """Nieznana ścieżka albo zła metoda: w logu sama metoda - surowy adres może zawierać identyfikatory."""
    call("GET", "/api/users/sekretne-id-42")
    call("DELETE", "/api/items/sekretne-id-43")
    lines = log_lines()
    access = [line for line in lines if line["message"] == "access"]
    assert [(line["route"], line["status"]) for line in access] == [
        ("GET (unmatched)", 404),
        ("DELETE (unmatched)", 404),
    ]
    assert "sekretne-id" not in json.dumps(lines)


def test_logs_never_contain_body(call, log_lines):
    for path in ("/api/created", "/api/invite", "/api/input", "/api/nie-ma"):
        call("POST", path, SECRET_BODY)
    assert "ala@example.com" not in json.dumps(log_lines())


def test_validation_fields_top_level_in_order():
    class Body(BaseModel):
        title: str
        price: Decimal
        tags: list[str]

    with pytest.raises(ValidationError) as caught:
        Body.model_validate({"price": "x", "tags": ["ok", 1]})
    assert validation_fields(caught.value) == ["title", "price", "tags"]
    assert validation_fields(caught.value, sort=True) == ["price", "tags", "title"]


def test_api_error_signature_unchanged():
    error = ApiError(400, "Niepoprawne pola", fields=["title"], code="x")
    assert (error.status, error.body) == (400, {"error": "Niepoprawne pola", "fields": ["title"], "code": "x"})


def test_routes_from_router_get_same_handling(log_lines):
    """Trasy z `Router` (routes/<domena>.py) dostają te same błędy, 404 i linię dostępu."""
    router = APIGatewayHttpRouter()

    @router.put("/api/friends/<user_id>")
    def accept(user_id: str):
        body = parse_input(Invite, parse_body(router.current_event.raw_event), "Podaj kod znajomego")
        return {"userId": user_id, "code": body.code}

    app = create_app(APIGatewayHttpResolver)
    app.include_router(router)
    assert isinstance(app, APIGatewayHttpResolver)

    ok = app.resolve(http_event("PUT", "/api/friends/u-1", '{"code": "WAW-1", "count": 2}'), CONTEXT)
    assert (ok["statusCode"], _body(ok)) == (200, {"userId": "u-1", "code": "WAW-1"})
    bad = app.resolve(http_event("PUT", "/api/friends/u-1", '{"count": "x"}'), CONTEXT)
    assert (bad["statusCode"], _body(bad)) == (400, {"error": "Podaj kod znajomego", "fields": ["code", "count"]})
    broken = app.resolve(http_event("PUT", "/api/friends/u-1", "{zły"), CONTEXT)
    assert (broken["statusCode"], _body(broken)) == (400, {"error": "Niepoprawny JSON"})
    routes = [line["route"] for line in log_lines() if line["message"] == "access"]
    assert routes == ["PUT /api/friends/{user_id}"] * 3


def test_parse_input_returns_model():
    assert parse_input(Invite, {"code": "WAW-1", "count": "2"}) == Invite(code="WAW-1", count=2)
    with pytest.raises(ApiError) as caught:
        parse_input(Invite, [])
    assert caught.value.body == {"error": "Niepoprawne dane", "fields": []}
