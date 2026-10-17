"""Worker ECS: pobiera eventy z SQS, normalizuje, taguje i zapisuje do docelowej tabeli DynamoDB.

Kończy działanie, gdy kolejka jest pusta (IDLE_POLLS pustych long-polli z rzędu) albo po SIGTERM
(np. przerwanie Fargate Spot). Nieprzetworzone wiadomości wracają do kolejki po visibility timeout,
a po 5 nieudanych próbach trafiają do DLQ.
"""

import hashlib
import html
import json
import logging
import os
import re
import signal
from datetime import datetime, timezone
from decimal import Decimal

import boto3

QUEUE_URL = os.environ["EVENTS_QUEUE_URL"]
EVENTS_TABLE = os.environ["EVENTS_TABLE"]
SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
WAIT_TIME_S = int(os.environ.get("WAIT_TIME_S", 20))
IDLE_POLLS = int(os.environ.get("IDLE_POLLS", 2))

SOURCE_PARTNER = "partner"
SOURCE_UM = "um_warszawa"

# Tagowanie regułowe (placeholder): tag -> fragmenty szukane w tytule i opisach.
KEYWORD_TAGS = {
    "dla-dzieci": ["dla dzieci", "dzieci", "rodzin", "maluch"],
    "koncert": ["koncert", "recital"],
    "teatr": ["teatr", "spektakl", "przedstawien"],
    "kino": ["film", "kino", "seans"],
    "wystawa": ["wystaw", "ekspozycj", "wernisaż"],
    "warsztaty": ["warsztat"],
    "sport": ["bieg", "turniej", "mecz", "zawody"],
    "plener": ["plener", "w parku", "na świeżym powietrzu"],
    "bezplatne": ["bezpłatn", "wstęp wolny", "darmow"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")
events_table = dynamodb.Table(EVENTS_TABLE)
submissions_table = dynamodb.Table(SUBMISSIONS_TABLE)

stopping = False


def _on_sigterm(signum, frame):
    global stopping
    stopping = True
    log.info("SIGTERM - kończę po bieżącej paczce")


def main():
    signal.signal(signal.SIGTERM, _on_sigterm)
    idle = processed = failed = 0

    while not stopping and idle < IDLE_POLLS:
        messages = sqs.receive_message(
            QueueUrl=QUEUE_URL, MaxNumberOfMessages=10, WaitTimeSeconds=WAIT_TIME_S
        ).get("Messages", [])
        if not messages:
            idle += 1
            continue
        idle = 0

        done = []
        for message in messages:
            try:
                process(json.loads(message["Body"], parse_float=Decimal))
                done.append(message)
            except Exception:
                failed += 1
                log.exception("Błąd przetwarzania wiadomości %s", message["MessageId"])

        if done:
            sqs.delete_message_batch(
                QueueUrl=QUEUE_URL,
                Entries=[{"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(done)],
            )
            processed += len(done)

    log.info("Koniec: przetworzono %d, błędy %d", processed, failed)
    return processed, failed


def process(message):
    source = message["source"]
    if source == SOURCE_PARTNER:
        record = dict(message["record"])
    elif source == SOURCE_UM:
        record = normalize_um(message["record"])
    else:
        raise ValueError(f"Nieznane źródło: {source}")

    now = _utc(datetime.now(timezone.utc))
    record["tags"] = tag_event(record)
    record["processedAt"] = now
    # put_item nadpisuje po id - ponowne dostarczenie tej samej wiadomości jest bezpieczne
    events_table.put_item(Item=record)

    if source == SOURCE_PARTNER:
        submissions_table.update_item(
            Key={"id": record["id"]},
            UpdateExpression="SET #status = :published, tags = :tags, processedAt = :now",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":published": "published", ":tags": record["tags"], ":now": now},
        )


# --- normalizacja rekordów z API UM Warszawy ---

def normalize_um(raw):
    url = raw.get("url")
    if not url:
        raise ValueError("Rekord UM bez url - nie da się wyznaczyć id")

    occurrence = [{**o, "from": _iso(o.get("from")), "to": _iso(o.get("to"))} for o in raw.get("occurrence", [])]
    starts = [_parse(o["from"]) for o in occurrence if o["from"]]
    ends = [_parse(o["to"] or o["from"]) for o in occurrence if o["to"] or o["from"]]
    now = _utc(datetime.now(timezone.utc))

    return {
        **raw,
        # deterministyczne id - ponowny import nadpisuje ten sam rekord
        "id": "um-" + hashlib.sha1(url.encode()).hexdigest()[:20],
        "source": SOURCE_UM,
        "occurrence": occurrence,
        "image": _https_image(raw.get("image")),
        "startsAt": _utc(min(starts)) if starts else None,
        "endsAt": _utc(max(ends)) if ends else None,
        "createdAt": raw.get("createdAt", now),
        "updatedAt": now,
    }


def _iso(value):
    """'2027-01-29T19:00:00+01' (format UM) -> '2027-01-29T19:00:00+01:00'."""
    if not value:
        return None
    return re.sub(r"([+-]\d{2})$", r"\1:00", value)


def _parse(value):
    return datetime.fromisoformat(value)


def _https_image(image):
    # Zdjęcia UM są pod http://, co na stronie HTTPS blokuje przeglądarka
    if not isinstance(image, dict):
        return image
    return {
        size: {**variant, "path": re.sub(r"^http://", "https://", variant.get("path") or "")}
        for size, variant in image.items()
    }


# --- tagowanie ---

def tag_event(record):
    tags = set()

    for key in ("category", "localization"):
        tags.update(_slug(item["name"]) for item in record.get(key) or [] if item.get("name"))

    content = " ".join(
        [record.get("title") or "", record.get("lead") or "", _strip_html(record.get("text") or "")]
        + [a.get("name") or "" for a in record.get("address") or []]
    ).lower()
    tags.update(tag for tag, needles in KEYWORD_TAGS.items() if any(n in content for n in needles))

    # Pora i dzień liczone w lokalnym czasie wydarzenia (z offsetem z occurrence)
    for occ in record.get("occurrence") or []:
        if occ.get("daily"):
            tags.add("codziennie")
        if not occ.get("from"):
            continue
        start = _parse(occ["from"])
        if start.weekday() >= 5:
            tags.add("weekend")
        if start.hour >= 17:
            tags.add("wieczorem")
        elif start.hour < 12:
            tags.add("rano")

    return sorted(tags)


def _strip_html(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


_PL = str.maketrans("ąćęłńóśźż", "acelnoszz")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().translate(_PL)).strip("-")


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    main()
