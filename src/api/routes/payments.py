"""Płatności za kredyty (mock bramki): lista, utworzenie, podgląd, potwierdzenie, anulowanie.

`<id>` w ścieżce = id płatności (w logu dostępu "{id}", bez wartości)."""

from decimal import Decimal
from typing import Any

from aws_lambda_powertools.event_handler.router import APIGatewayRouter

from codzis_common.http import parse_body
from payments import cancel_payment, confirm_payment, create_payment, get_payment, list_payments
from routes import current_partner
from schemas import parse_payment

router = APIGatewayRouter()


@router.get("/payments")
def get_payments() -> dict[str, Any]:
    return list_payments(current_partner(router))


@router.post("/payments")
def post_payment() -> tuple[dict[str, Any], int]:
    partner = current_partner(router)
    body = parse_payment(parse_body(router.current_event.raw_event, parse_float=Decimal))
    return create_payment(partner, body.package), 201


@router.get("/payments/<id>")
def get_one(id: str) -> dict[str, Any]:
    return get_payment(current_partner(router), id)


@router.post("/payments/<id>/confirm")
def post_confirm(id: str) -> dict[str, Any]:
    return confirm_payment(current_partner(router), id)


@router.post("/payments/<id>/cancel")
def post_cancel(id: str) -> dict[str, Any]:
    return cancel_payment(current_partner(router), id)
