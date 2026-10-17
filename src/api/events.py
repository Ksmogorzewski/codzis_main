"""Ogłoszenia partnera: lista, dodanie (walidacja formularza -> rekord schematu v1 -> kolejka taggera)."""

import html
import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from codzis_common.http import ApiError, json_default, now_iso
from config import (
    CATEGORIES,
    CURRENCY,
    DISTRICTS,
    EVENT_COST,
    EVENTS_QUEUE_URL,
    MAX_PHOTO_BYTES,
    PHOTOS_BUCKET,
    PUBLIC_BASE_URL,
    SUBMISSIONS_TABLE,
    UPLOAD_EXPIRES_S,
)
from store import credit_update, ddb, query_by_partner, s3, sqs, submissions_table, transact

SOURCE = "partner"  # źródła miejskie (importer): um_kalendarz | um_sport
SCHEMA_VERSION = 1

# Pola tekstowe formularza: nazwa -> (wymagane, max długość). Pozostałe pola są ignorowane.
TEXT_FIELDS = {
    "title": (True, 200),
    "lead": (True, 500),
    "text": (False, 5000),
    "venue": (True, 200),
    "street": (False, 200),
    "streetNumber": (False, 20),
    "url": (False, 500),
    "ticketUrl": (False, 500),
}

# Parametry, które partner deklaruje wprost. Wartości = dokładnie opcje z taksonomii taggera
# (tagger/prompt.py -> DIMENSIONS); tagger nadpisuje nimi zgadywania modelu.
# Wymiar -> (wymagany, wiele wartości, opcje)
DECLARED_FIELDS = {
    "cost": (True, False, ["Bezpłatne", "Płatne"]),
    "registration": (True, False, ["Wstęp wolny", "Wymagane zapisy / rejestracja", "Wymagany bilet"]),
    "setting": (True, False, ["W pomieszczeniu", "Na zewnątrz", "W pomieszczeniu i na zewnątrz"]),
    "audience": (
        False,
        True,
        ["Dzieci (0-12)", "Młodzież (13-17)", "Dorośli (18-64)", "Seniorzy (65+)", "Rodziny / wszystkie grupy"],
    ),
    "accessibility": (
        False,
        True,
        [
            "Dostępne dla osób z niepełnosprawnością ruchową",
            "Tłumaczenie na PJM",
            "Audiodeskrypcja",
            "Przyjazne sensorycznie",
        ],
    ),
}
MAX_PRICE = 100_000

PHOTO_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def list_events(partner):
    # Zgłoszenia partnera ze statusem: queued (czeka na worker) / published (otagowane, w tabeli events)
    return {"items": query_by_partner(submissions_table, partner)}


def create_event(partner, body):
    data = _event_input(body)

    content_type = body.get("photoContentType")
    if content_type not in PHOTO_TYPES:
        raise ApiError(400, "Nieobsługiwany typ zdjęcia", allowed=list(PHOTO_TYPES))

    event_id = str(uuid.uuid4())
    photo_key = f"photos/{event_id}/photo.{PHOTO_TYPES[content_type]}"
    record = _event_record(event_id, partner, data, f"{PUBLIC_BASE_URL}/{photo_key}")

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


def _event_input(body):
    """Walidacja formularza -> dane do rekordu albo ApiError 400 z listą błędnych pól (`fields`)."""
    errors = []
    data: dict[str, Any] = {}

    for name, (required, max_len) in TEXT_FIELDS.items():
        value = body.get(name)
        if _is_blank(value):
            data[name] = None
            if required:
                errors.append(name)
        elif not isinstance(value, str) or len(value) > max_len:
            errors.append(name)
        else:
            data[name] = value.strip()

    for name in ("url", "ticketUrl"):
        if data.get(name) and not re.match(r"https?://", data[name]):
            errors.append(name)

    data["declared"] = {}
    for name, (required, multi, options) in DECLARED_FIELDS.items():
        value = body.get(name)
        if multi:
            values = value if isinstance(value, list) else []
            if not isinstance(value, (list, type(None))) or any(v not in options for v in values):
                errors.append(name)
            elif values:
                data["declared"][name] = [o for o in options if o in values]  # kolejność jak w opcjach, bez duplikatów
            elif required:
                errors.append(name)
        elif value in options:
            data["declared"][name] = value
        elif required or not _is_blank(value):
            errors.append(name)

    data["price"] = None
    price_min, price_max = (
        _price(body.get("priceMin"), errors, "priceMin"),
        _price(body.get("priceMax"), errors, "priceMax"),
    )
    cost = data["declared"].get("cost")
    if (price_min is not None or price_max is not None) and cost:  # bez kosztu błąd zgłasza już pole cost
        if cost != "Płatne":
            errors.append("priceMin" if price_min is not None else "priceMax")  # cena przy wydarzeniu bezpłatnym
        elif price_min is not None and price_max is not None and price_max < price_min:
            errors.append("priceMax")
        else:
            data["price"] = {"min": price_min, "max": price_max, "currency": CURRENCY}

    data["category"] = body.get("category")
    if data["category"] not in CATEGORIES:
        errors.append("category")

    data["district"] = body.get("district")
    if data["district"] not in DISTRICTS:
        errors.append("district")

    data["startsAt"] = _parse_datetime(body.get("startsAt"))
    data["endsAt"] = _parse_datetime(body.get("endsAt"))
    if not data["startsAt"]:
        errors.append("startsAt")
    if body.get("endsAt") and (not data["endsAt"] or (data["startsAt"] and data["endsAt"] < data["startsAt"])):
        errors.append("endsAt")
    last = data["endsAt"] or data["startsAt"]
    if last and last < datetime.now(UTC):
        errors.append("endsAt" if data["endsAt"] else "startsAt")

    if errors:
        raise ApiError(400, "Niepoprawne lub brakujące pola", fields=sorted(set(errors)))
    return data


def _price(value, errors, name):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        price = Decimal(str(value))
    except Exception:
        errors.append(name)
        return None
    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        errors.append(name)
        return None
    return price.quantize(Decimal("0.01"))


def _event_record(event_id, partner, data, photo_url):
    """Rekord we wspólnym schemacie v1 (opis pól: src/importer/schema.py)."""
    starts, ends = data["startsAt"], data["endsAt"]
    now = now_iso()
    address = " ".join(filter(None, [data["street"], data["streetNumber"]])) or None
    return {
        "id": event_id,
        "origin": SOURCE,  # partner | um_warszawa - skąd pochodzi event
        "source": SOURCE,
        "kind": "event",
        "schemaVersion": SCHEMA_VERSION,
        "title": data["title"],
        "lead": data["lead"],
        "text": _to_html(data["text"]),
        "url": data["url"],
        "category": [{"id": None, "name": data["category"]}],
        "audience": data["declared"].get("audience", []),
        "district": data["district"],
        "online": False,
        "venue": {"name": data["venue"], "address": address},
        "location": None,  # brak współrzędnych - do uzupełnienia geokodowaniem
        "occurrences": [{"start": starts.isoformat(), "end": ends.isoformat() if ends else None, "allDay": False}],
        "schedule": [],
        "startsAt": _utc(starts),
        "endsAt": _utc(ends or starts),
        "imageUrl": photo_url,
        "attributes": {"price": data["price"], "ticketUrl": data["ticketUrl"]},
        # tylko partner: parametry zadeklarowane wprost - tagger przepisuje je do tags zamiast zgadywać
        "declared": data["declared"],
        "partnerId": partner["partnerId"],
        "partnerName": partner["partnerName"],
        "createdAt": now,
        "updatedAt": now,
    }


def _parse_datetime(value):
    """ISO 8601 z offsetem strefy, np. 2027-01-29T19:00:00+01:00."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _utc(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_html(text):
    # Zwykły tekst partnera -> akapity HTML, jak pole "text" w API Warszawy.
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())
