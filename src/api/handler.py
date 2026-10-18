"""API panelu partnera (REST API v1, proxy /{proxy+}, klucz API partnera).

    GET  /me                       profil partnera: saldo kredytów, koszt ogłoszenia, opcje formularza
                                   (pierwsze wywołanie zakłada rekord z kredytami startowymi)
    GET  /events                   ostatnie zgłoszenia partnera (events.py)
    POST /events                   nowe ogłoszenie: walidacja, -1 kredyt, kolejka taggera, presigned POST zdjęcia
    GET  /payments                 ostatnie płatności partnera (payments.py)
    POST /payments                 {"package": id} -> płatność pending + redirectUrl (mock bramki)
    GET  /payments/{id}            podgląd płatności
    POST /payments/{id}/confirm    rozliczenie: dodaje kredyty (raz; ponownie -> 409)
    POST /payments/{id}/cancel     anulowanie płatności pending

Pliki: handler.py (routing), events.py (ogłoszenia i walidacja), payments.py (płatności),
store.py (klienty AWS, transakcje i kredyty), config.py (zmienne środowiskowe).
"""

from decimal import Decimal

from codzis_common.http import ApiError, handle_request, parse_body, response
from config import EVENT_COST, PARTNERS, STARTER_CREDITS
from events import DECLARED_FIELDS, create_event, list_events
from payments import cancel_payment, confirm_payment, create_payment, get_payment, list_payments
from store import partners_table


def handler(event, context):
    """Punkt wejścia: każdy błąd kończy się odpowiedzią JSON (inny niż ApiError -> 500 z requestId)."""
    return handle_request(event, _route_key(event), lambda: route(event))


def route(event):
    # API GW wpuszcza tu tylko żądania z poprawnym kluczem, więc apiKeyId identyfikuje partnera.
    partner = _partner(event)
    match (event.get("httpMethod"), *_path(event)):
        case ("GET", "me"):
            return response(200, get_profile(partner))
        case ("GET", "events"):
            return response(200, list_events(partner))
        case ("POST", "events"):
            return response(201, create_event(partner, _body(event)))
        case ("GET", "payments"):
            return response(200, list_payments(partner))
        case ("POST", "payments"):
            return response(201, create_payment(partner, _body(event)))
        case ("GET", "payments", payment_id):
            return response(200, get_payment(partner, payment_id))
        case ("POST", "payments", payment_id, "confirm"):
            return response(200, confirm_payment(partner, payment_id))
        case ("POST", "payments", payment_id, "cancel"):
            return response(200, cancel_payment(partner, payment_id))
    raise ApiError(404, "Nie znaleziono")


def get_profile(partner):
    # Pierwsze logowanie zakłada rekord partnera z kredytami startowymi.
    item = partners_table.update_item(
        Key={"partnerId": partner["partnerId"]},
        UpdateExpression="SET partnerName = :name, credits = if_not_exists(credits, :start)",
        ExpressionAttributeValues={":name": partner["partnerName"], ":start": STARTER_CREDITS},
        ReturnValues="ALL_NEW",
    )["Attributes"]
    options = {name: opts for name, (_, _, opts) in DECLARED_FIELDS.items()}
    return {**partner, "credits": item["credits"], "eventCost": EVENT_COST, "formOptions": options}


def _partner(event):
    key_id = event["requestContext"]["identity"]["apiKeyId"]
    return {"partnerId": key_id, "partnerName": PARTNERS.get(key_id, key_id)}


def _path(event):
    return ((event.get("pathParameters") or {}).get("proxy") or "").strip("/").split("/")


def _route_key(event):
    """Trasa do logu dostępu, np. "POST /payments/{id}/confirm" (bez identyfikatorów z adresu)."""
    path = _path(event)
    if len(path) > 1 and path[0] == "payments":
        path = ["payments", "{id}", *path[2:]]
    return f"{event.get('httpMethod')} /{'/'.join(path)}"


def _body(event):
    # Liczby (ceny) jako Decimal - bez utraty dokładności przy zapisie w DynamoDB.
    return parse_body(event, parse_float=Decimal)
