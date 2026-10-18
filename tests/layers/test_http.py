"""Wspólny moduł warstwy: src/layers/common/python/codzis_common/http.py."""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from codzis_common.http import SERVER_ERROR, ApiError, handle_request, json_default, now_iso, parse_body, response


def test_api_error_body_and_status():
    error = ApiError(400, "Niepoprawne pola", fields=["title"], code="x")
    assert error.status == 400
    assert error.body == {"error": "Niepoprawne pola", "fields": ["title"], "code": "x"}
    assert str(error) == "Niepoprawne pola"


def test_parse_body_object():
    assert parse_body({"body": '{"a": 1.5}'}) == {"a": 1.5}


@pytest.mark.parametrize("event", [{}, {"body": None}, {"body": ""}])
def test_parse_body_empty_is_empty_object(event):
    assert parse_body(event) == {}


def test_parse_body_decimal_floats():
    body = parse_body({"body": '{"price": 19.99, "count": 2}'}, parse_float=Decimal)
    assert body == {"price": Decimal("19.99"), "count": 2}
    assert isinstance(body["price"], Decimal)


@pytest.mark.parametrize(
    ("raw", "message"),
    [("{zły", "Niepoprawny JSON"), ("[1]", "Oczekiwano obiektu JSON"), ('"tekst"', "Oczekiwano obiektu JSON")],
)
def test_parse_body_errors(raw, message):
    with pytest.raises(ApiError) as caught:
        parse_body({"body": raw})
    assert caught.value.status == 400
    assert caught.value.body == {"error": message}


def test_json_default():
    assert json_default(Decimal("3")) == 3
    assert isinstance(json_default(Decimal("3.0")), int)
    assert json_default(Decimal("2.5")) == 2.5
    with pytest.raises(TypeError):
        json_default(object())


def test_response():
    result = response(201, {"name": "Śródmieście", "price": Decimal("12.50"), "n": Decimal(1)})
    assert result["statusCode"] == 201
    assert result["headers"] == {"Content-Type": "application/json"}
    assert "Śródmieście" in result["body"]
    assert json.loads(result["body"]) == {"name": "Śródmieście", "price": 12.5, "n": 1}


def test_now_iso_is_utc():
    offset = datetime.fromisoformat(now_iso()).utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


# --- handle_request: catch-all i log dostępu ---

EVENT = {"requestContext": {"requestId": "req-1"}, "body": '{"email": "ala@example.com"}'}


def _ok():
    return response(200, {"ok": True})


def _api_error():
    raise ApiError(409, "Podaj imię", code="name_required")


def _boom():
    raise RuntimeError("awaria")


def _records(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "codzis.http"]


def test_handle_request_passes_response(caplog):
    caplog.set_level("INFO", logger="codzis.http")
    result = handle_request(EVENT, "GET /api/me", _ok)
    assert result == response(200, {"ok": True})
    [access] = _records(caplog)
    assert access["route"] == "GET /api/me"
    assert access["status"] == 200
    assert access["requestId"] == "req-1"
    assert isinstance(access["durationMs"], int)
    assert set(access) == {"route", "status", "durationMs", "requestId"}


def test_handle_request_api_error_unchanged_and_warning(caplog):
    caplog.set_level("INFO", logger="codzis.http")
    result = handle_request(EVENT, "GET /api/friends", _api_error)
    assert result == response(409, {"error": "Podaj imię", "code": "name_required"})
    warning = next(r for r in caplog.records if r.levelname == "WARNING")
    assert json.loads(warning.getMessage()) == {
        "route": "GET /api/friends",
        "status": 409,
        "code": "name_required",
        "requestId": "req-1",
    }
    assert _records(caplog)[-1]["status"] == 409


def test_handle_request_unexpected_error_is_500_with_request_id(caplog):
    caplog.set_level("INFO", logger="codzis.http")
    result = handle_request(EVENT, "GET /api/me", _boom)
    assert result["statusCode"] == 500
    assert result["headers"] == {"Content-Type": "application/json"}
    assert json.loads(result["body"]) == {"error": SERVER_ERROR, "requestId": "req-1"}
    error = next(r for r in caplog.records if r.levelname == "ERROR")
    assert error.exc_info is not None  # pełny traceback w CloudWatch
    assert json.loads(error.getMessage())["route"] == "GET /api/me"
    assert _records(caplog)[-1]["status"] == 500


def test_handle_request_without_request_id():
    result = handle_request({}, None, _boom)
    assert json.loads(result["body"]) == {"error": SERVER_ERROR, "requestId": None}


def test_handle_request_never_logs_body(caplog):
    caplog.set_level("INFO", logger="codzis.http")
    for run in (_ok, _api_error, _boom):
        handle_request(EVENT, "PUT /api/profile", run)
    assert "ala@example.com" not in caplog.text
