"""Ogłoszenia partnera: GET /events (ostatnie zgłoszenia), POST /events (nowe ogłoszenie)."""

from decimal import Decimal
from typing import Any

from aws_lambda_powertools.event_handler.router import APIGatewayRouter

from codzis_common.http import parse_body
from events import create_event, list_events
from routes import current_partner
from schemas import parse_event

router = APIGatewayRouter()


@router.get("/events")
def get_events() -> dict[str, Any]:
    return list_events(current_partner(router))


@router.post("/events")
def post_event() -> tuple[dict[str, Any], int]:
    partner = current_partner(router)
    # Liczby (ceny) jako Decimal - bez utraty dokładności przy zapisie w DynamoDB.
    form = parse_event(parse_body(router.current_event.raw_event, parse_float=Decimal))
    return create_event(partner, form), 201
