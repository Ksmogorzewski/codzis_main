import html
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
EVENTS_QUEUE_URL = os.environ["EVENTS_QUEUE_URL"]
PARTNERS_TABLE = os.environ["PARTNERS_TABLE"]
PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
PHOTOS_BUCKET = os.environ["PHOTOS_BUCKET"]
MAX_PHOTO_BYTES = int(os.environ.get("MAX_PHOTO_BYTES", 5 * 1024 * 1024))
EVENT_COST = int(os.environ.get("EVENT_COST_CREDITS", 1))
STARTER_CREDITS = int(os.environ.get("STARTER_CREDITS", 0))
CREDIT_PACKAGES = json.loads(os.environ["CREDIT_PACKAGES"], parse_float=Decimal)  # id -> {name, credits, price}
CURRENCY = os.environ.get("CURRENCY", "PLN")
PARTNERS = json.loads(os.environ.get("PARTNERS", "{}"))  # apiKeyId -> nazwa partnera
CATEGORIES = json.loads(os.environ["CATEGORIES"])
DISTRICTS = json.loads(os.environ["DISTRICTS"])
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]  # zdjęcia serwuje CloudFront pod /photos/*
REGION = os.environ["AWS_REGION"]
UPLOAD_EXPIRES_S = 300
LIST_LIMIT = 50

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
    "audience": (False, True, ["Dzieci (0-12)", "Młodzież (13-17)", "Dorośli (18-64)", "Seniorzy (65+)", "Rodziny / wszystkie grupy"]),
    "accessibility": (False, True, [
        "Dostępne dla osób z niepełnosprawnością ruchową",
        "Tłumaczenie na PJM",
        "Audiodeskrypcja",
        "Przyjazne sensorycznie",
    ]),
}
MAX_PRICE = 100_000

PHOTO_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

dynamodb = boto3.resource("dynamodb")
submissions_table = dynamodb.Table(SUBMISSIONS_TABLE)
partners_table = dynamodb.Table(PARTNERS_TABLE)
payments_table = dynamodb.Table(PAYMENTS_TABLE)
# Klient zasobu (nie boto3.client) - transakcje przyjmują zwykłe typy Pythona.
ddb = dynamodb.meta.client
sqs = boto3.client("sqs")

# Regionalny endpoint - globalny potrafi zwracać 307 dla świeżych bucketów, co psuje CORS.
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.body = {"error": message, **extra}


def handler(event, context):
    # API GW wpuszcza tu tylko żądania z poprawnym kluczem, więc apiKeyId identyfikuje partnera.
    partner = _partner(event)
    method = event.get("httpMethod")
    path = ((event.get("pathParameters") or {}).get("proxy") or "").strip("/").split("/")

    try:
        match (method, *path):
            case ("GET", "me"):
                return _response(200, get_profile(partner))
            case ("GET", "events"):
                return _response(200, list_events(partner))
            case ("POST", "events"):
                return _response(201, create_event(partner, _body(event)))
            case ("GET", "payments"):
                return _response(200, list_payments(partner))
            case ("POST", "payments"):
                return _response(201, create_payment(partner, _body(event)))
            case ("GET", "payments", payment_id):
                return _response(200, get_payment(partner, payment_id))
            case ("POST", "payments", payment_id, "confirm"):
                return _response(200, confirm_payment(partner, payment_id))
            case ("POST", "payments", payment_id, "cancel"):
                return _response(200, cancel_payment(partner, payment_id))
        raise ApiError(404, "Nie znaleziono")
    except ApiError as e:
        return _response(e.status, e.body)


# --- profil ---

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


# --- ogłoszenia ---

def list_events(partner):
    # Zgłoszenia partnera ze statusem: queued (czeka na worker) / published (otagowane, w tabeli events)
    return {"items": _query_by_partner(submissions_table, partner)}


def create_event(partner, body):
    data = _event_input(body)

    content_type = body.get("photoContentType")
    if content_type not in PHOTO_TYPES:
        raise ApiError(400, "Nieobsługiwany typ zdjęcia", allowed=list(PHOTO_TYPES))

    event_id = str(uuid.uuid4())
    photo_key = f"photos/{event_id}/photo.{PHOTO_TYPES[content_type]}"
    record = _event_record(event_id, partner, data, f"{PUBLIC_BASE_URL}/{photo_key}")

    # Odjęcie kredytu i zapis zgłoszenia razem albo wcale.
    _transact(
        [
            _credit_update(partner, -EVENT_COST),
            {"Put": {"TableName": SUBMISSIONS_TABLE, "Item": {**record, "status": "queued"}}},
        ],
        ApiError(402, "Brak kredytów", required=EVENT_COST),
    )

    # Do tabeli docelowej rekord trafia przez kolejkę i worker ECS (tagowanie).
    try:
        sqs.send_message(
            QueueUrl=EVENTS_QUEUE_URL,
            # Kontrakt taggera: body = JSON array rekordów; "source" i "id" są w rekordzie
            MessageBody=json.dumps([record], ensure_ascii=False, default=_json_default),
        )
    except Exception:
        # Kompensacja: zwrot kredytu i usunięcie zgłoszenia
        ddb.transact_write_items(
            TransactItems=[
                _credit_update(partner, EVENT_COST, require_funds=False),
                {"Delete": {"TableName": SUBMISSIONS_TABLE, "Key": {"id": event_id}}},
            ]
        )
        raise ApiError(503, "Nie udało się przyjąć ogłoszenia, spróbuj ponownie")

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
    errors = []
    data = {}

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
    price_min, price_max = _price(body.get("priceMin"), errors, "priceMin"), _price(body.get("priceMax"), errors, "priceMax")
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
    if last and last < datetime.now(timezone.utc):
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
    now = _now()
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
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_html(text):
    # Zwykły tekst partnera -> akapity HTML, jak pole "text" w API Warszawy.
    if not text:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


# --- płatności (mock bramka) ---

def list_payments(partner):
    return {"items": _query_by_partner(payments_table, partner)}


def create_payment(partner, body):
    package_id = body.get("package")
    package = CREDIT_PACKAGES.get(package_id)
    if not package:
        raise ApiError(400, "Nieznany pakiet", allowed=list(CREDIT_PACKAGES))

    item = {
        "id": str(uuid.uuid4()),
        "partnerId": partner["partnerId"],
        "package": package_id,
        "packageName": package["name"],
        "credits": int(package["credits"]),
        "amount": package["price"],
        "currency": CURRENCY,
        "status": "pending",
        "createdAt": _now(),
    }
    payments_table.put_item(Item=item)
    # Prawdziwa bramka zwróciłaby tu swój URL; mock to statyczna strona portalu.
    return {**item, "redirectUrl": f"/mock-pay.html?id={item['id']}"}


def get_payment(partner, payment_id):
    item = payments_table.get_item(Key={"id": payment_id}).get("Item")
    if not item or item["partnerId"] != partner["partnerId"]:
        raise ApiError(404, "Nie znaleziono płatności")
    return item


def confirm_payment(partner, payment_id):
    # W prawdziwej integracji to byłby webhook bramki weryfikowany podpisem, nie wywołanie partnera.
    payment = get_payment(partner, payment_id)
    paid_at = _now()
    _transact(
        [
            _payment_transition(payment_id, "paid", paid_at),
            _credit_update(partner, int(payment["credits"])),
        ],
        ApiError(409, "Płatność została już rozliczona"),
    )
    return {**payment, "status": "paid", "paidAt": paid_at}


def cancel_payment(partner, payment_id):
    payment = get_payment(partner, payment_id)
    _transact(
        [_payment_transition(payment_id, "cancelled", _now())],
        ApiError(409, "Płatność została już rozliczona"),
    )
    return {**payment, "status": "cancelled"}


def _credit_update(partner, delta, require_funds=True):
    update = {
        "TableName": PARTNERS_TABLE,
        "Key": {"partnerId": partner["partnerId"]},
        "UpdateExpression": "ADD credits :delta",
        "ExpressionAttributeValues": {":delta": delta},
    }
    if delta < 0 and require_funds:
        update["ConditionExpression"] = "credits >= :needed"
        update["ExpressionAttributeValues"][":needed"] = -delta
    return {"Update": update}


def _payment_transition(payment_id, status, at):
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


# --- helpers ---

def _transact(items, condition_error):
    try:
        ddb.transact_write_items(TransactItems=items)
    except ddb.exceptions.TransactionCanceledException as e:
        reasons = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
        if "ConditionalCheckFailed" in reasons:
            raise condition_error
        raise ApiError(409, "Konflikt zapisu, spróbuj ponownie")


def _query_by_partner(table, partner):
    return table.query(
        IndexName="byPartner",
        KeyConditionExpression=Key("partnerId").eq(partner["partnerId"]),
        ScanIndexForward=False,
        Limit=LIST_LIMIT,
    )["Items"]


def _partner(event):
    key_id = event["requestContext"]["identity"]["apiKeyId"]
    return {"partnerId": key_id, "partnerName": PARTNERS.get(key_id, key_id)}


def _body(event):
    try:
        body = json.loads(event.get("body") or "{}", parse_float=Decimal)
    except json.JSONDecodeError:
        raise ApiError(400, "Niepoprawny JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "Oczekiwano obiektu JSON")
    return body


def _now():
    return datetime.now(timezone.utc).isoformat()


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Nie da się zserializować {type(value).__name__}")


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, default=_json_default),
    }
