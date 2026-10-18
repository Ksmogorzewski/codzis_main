"""Płatności za kredyty (mock bramki): utworzenie, podgląd, potwierdzenie (dodaje kredyty), anulowanie."""

import uuid
from typing import Any

from codzis_common.http import ApiError, now_iso
from config import CREDIT_PACKAGES, CURRENCY, PAYMENTS_TABLE
from schemas import Partner
from store import credit_update, payments_table, query_by_partner, transact


def list_payments(partner: Partner) -> dict[str, Any]:
    return {"items": query_by_partner(payments_table, partner)}


def create_payment(partner: Partner, package_id: str) -> dict[str, Any]:
    """Płatność pending za pakiet (id sprawdzony w `schemas.parse_payment`) + adres bramki."""
    package = CREDIT_PACKAGES[package_id]
    item = {
        "id": str(uuid.uuid4()),
        "partnerId": partner["partnerId"],
        "package": package_id,
        "packageName": package["name"],
        "credits": int(package["credits"]),
        "amount": package["price"],
        "currency": CURRENCY,
        "status": "pending",
        "createdAt": now_iso(),
    }
    payments_table.put_item(Item=item)
    # Prawdziwa bramka zwróciłaby tu swój URL; mock to statyczna strona portalu.
    return {**item, "redirectUrl": f"/mock-pay.html?id={item['id']}"}


def get_payment(partner: Partner, payment_id: str) -> dict[str, Any]:
    item = payments_table.get_item(Key={"id": payment_id}).get("Item")
    if not item or item["partnerId"] != partner["partnerId"]:
        raise ApiError(404, "Nie znaleziono płatności")
    return item


def confirm_payment(partner: Partner, payment_id: str) -> dict[str, Any]:
    # W prawdziwej integracji to byłby webhook bramki weryfikowany podpisem, nie wywołanie partnera.
    payment = get_payment(partner, payment_id)
    paid_at = now_iso()
    transact(
        [
            _payment_transition(payment_id, "paid", paid_at),
            credit_update(partner, int(payment["credits"])),
        ],
        ApiError(409, "Płatność została już rozliczona"),
    )
    return {**payment, "status": "paid", "paidAt": paid_at}


def cancel_payment(partner: Partner, payment_id: str) -> dict[str, Any]:
    payment = get_payment(partner, payment_id)
    transact(
        [_payment_transition(payment_id, "cancelled", now_iso())],
        ApiError(409, "Płatność została już rozliczona"),
    )
    return {**payment, "status": "cancelled"}


def _payment_transition(payment_id, status, at):
    """Zmiana statusu tylko z pending - druga próba rozliczenia kończy się 409."""
    return {
        "Update": {
            "TableName": PAYMENTS_TABLE,
            "Key": {"id": payment_id},
            "UpdateExpression": "SET #status = :new, updatedAt = :at",
            "ConditionExpression": "#status = :pending",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":new": status, ":at": at, ":pending": "pending"},
        }
    }
