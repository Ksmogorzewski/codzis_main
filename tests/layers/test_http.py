"""Wspólny moduł warstwy: src/layers/common/python/codzis_common/http.py."""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from codzis_common.http import ApiError, json_default, now_iso, parse_body, response


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
