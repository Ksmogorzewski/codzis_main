"""Ogłoszenia partnera: lista, dodanie (formularz sprawdzony w schemas.parse_event -> rekord schematu v1 ->
kolejka taggera)."""

import html
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from codzis_common.http import ApiError, json_default, now_iso
from config import (
    CURRENCY,
    EVENT_COST,
    EVENTS_QUEUE_URL,
    MAX_PHOTO_BYTES,
    PHOTOS_BUCKET,
    PUBLIC_BASE_URL,
    SUBMISSIONS_TABLE,
    UPLOAD_EXPIRES_S,
)
from schemas import PHOTO_TYPES, EventBody, Partner
from store import credit_update, ddb, query_by_partner, s3, sqs, submissions_table, transact

SOURCE = "partner"  # źródła miejskie (importer): um_kalendarz | um_sport
SCHEMA_VERSION = 1


def list_events(partner: Partner) -> dict[str, Any]:
    # Zgłoszenia partnera ze statusem: queued (czeka na worker) / published (otagowane, w tabeli events)
    return {"items": query_by_partner(submissions_table, partner)}


def create_event(partner: Partner, form: EventBody) -> dict[str, Any]:
    content_type = form.photoContentType
    if content_type is None:
        raise ApiError(400, "Nieobsługiwany typ zdjęcia", allowed=list(PHOTO_TYPES))

    event_id = str(uuid.uuid4())
    photo_key = f"photos/{event_id}/photo.{PHOTO_TYPES[content_type]}"
    record = _event_record(event_id, partner, form, f"{PUBLIC_BASE_URL}/{photo_key}")

    # Odjęcie kredytu i zapis zgłoszenia razem albo wcale.
    transact(
        [
            credit_update(partner, -EVENT_COST),
            {"Put": {"TableName": SUBMISSIONS_TABLE, "Item": {**record, "status": "queued"}}},
        ],
        ApiError(402, "Brak kredytów", required=EVENT_COST),
    )

    # Do tabeli docelowej rekord trafia przez kolejkę i worker ECS (tagowanie).
    try:
        sqs.send_message(
            QueueUrl=EVENTS_QUEUE_URL,
            # Kontrakt taggera: body = JSON array rekordów; "source" i "id" są w rekordzie
            MessageBody=json.dumps([record], ensure_ascii=False, default=json_default),
        )
    except Exception:
        # Kompensacja: zwrot kredytu i usunięcie zgłoszenia
        ddb.transact_write_items(
            TransactItems=[
                credit_update(partner, EVENT_COST, require_funds=False),
                {"Delete": {"TableName": SUBMISSIONS_TABLE, "Key": {"id": event_id}}},
            ]
        )
        raise ApiError(503, "Nie udało się przyjąć ogłoszenia, spróbuj ponownie") from None

    upload = s3.generate_presigned_post(
        Bucket=PHOTOS_BUCKET,
        Key=photo_key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, MAX_PHOTO_BYTES],
        ],
        ExpiresIn=UPLOAD_EXPIRES_S,
    )
    return {"id": event_id, "upload": upload}


def _event_record(event_id: str, partner: Partner, form: EventBody, photo_url: str) -> dict[str, Any]:
    """Rekord we wspólnym schemacie v1 (opis pól: src/importer/schema.py)."""
    starts, ends = form.startsAt, form.endsAt
    now = now_iso()
    address = " ".join(filter(None, [form.street, form.streetNumber])) or None
    return {
        "id": event_id,
        "origin": SOURCE,  # partner | um_warszawa - skąd pochodzi event
        "source": SOURCE,
        "kind": "event",
        "schemaVersion": SCHEMA_VERSION,
        "title": form.title,
        "lead": form.lead,
        "text": _to_html(form.text),
        "url": form.url,
        "category": [{"id": None, "name": form.category}],
        "audience": form.audience,
        "district": form.district,
        "online": False,
        "venue": {"name": form.venue, "address": address},
        "location": None,  # brak współrzędnych - do uzupełnienia geokodowaniem
        "occurrences": [{"start": starts.isoformat(), "end": ends.isoformat() if ends else None, "allDay": False}],
        "schedule": [],
        "startsAt": _utc(starts),
        "endsAt": _utc(ends or starts),
        "imageUrl": photo_url,
        "attributes": {"price": _price(form), "ticketUrl": form.ticketUrl},
        # tylko partner: parametry zadeklarowane wprost - tagger przepisuje je do tags zamiast zgadywać
        "declared": form.declared(),
        "partnerId": partner["partnerId"],
        "partnerName": partner["partnerName"],
        "createdAt": now,
        "updatedAt": now,
    }


def _price(form: EventBody) -> dict[str, Any] | None:
    # Cena tylko przy wydarzeniu płatnym - inną kombinację odrzuca schemas.parse_event.
    if form.priceMin is None and form.priceMax is None:
        return None
    return {"min": form.priceMin, "max": form.priceMax, "currency": CURRENCY}


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_html(text: str | None) -> str:
    # Zwykły tekst partnera -> akapity HTML, jak pole "text" w API Warszawy.
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)
