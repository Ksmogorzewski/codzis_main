"""Wydarzenia demo pod prezentację WarsawNow (dane: demo_events.json).

Rekordy w schemacie v1 (schema.py) idą zwykłą drogą: SQS -> tagger -> codzis-events -> indeks
rekomendera. Wszystkie wymiary tagów są zadeklarowane wprost (pole "declared", jak u partnerów),
więc tagger zostawia dokładnie te wartości. Terminy liczone są względem --start (domyślnie teraz),
żeby zawsze było coś na dziś, jutro i weekend. Wydarzenia rozpoznasz po origin = source = "demo"
i id "demo-…"; po terminie usuwa je TTL tabeli events, od ręki --delete.

    python demo.py --dry-run                   # podgląd rekordów (bez AWS)
    python demo.py --start 2026-10-18T14:00    # wysyłka na kolejkę taggera, terminy od 14:00
    python demo.py --wait                      # ... i czekanie, aż tagger zapisze wszystkie
    python demo.py --reset-sets                # zapisane zestawy rekomendacji do przeliczenia
    python demo.py --delete                    # usunięcie wydarzeń demo z tabeli events

Zmienne: SQS_QUEUE_URL (wysyłka), EVENTS_TABLE (--wait, --delete), RESULTS_TABLE (--reset-sets).
Całość z wdrożonej infry: scripts/demo-events.sh.
"""

import argparse
import html
import json
import logging
import os
import sys
import time as clock
from datetime import date, datetime, time, timedelta
from pathlib import Path

from schema import DAYS, WARSAW, content_hash, finalize, make_id, now_utc

DATA = Path(__file__).with_name("demo_events.json")
ORIGIN = "demo"  # origin i source wydarzeń demo
RECORDS_PER_MESSAGE = 20
IMAGE_URL = "https://images.unsplash.com/photo-{}?w=1200&q=75&auto=format&fit=crop"
WAIT_SECONDS = 600  # dispatcher co minutę + start taska taggera + tagowanie

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("demo")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Wydarzenia demo -> SQS (tagger)")
    parser.add_argument("--start", help="początek prezentacji, RRRR-MM-DDTHH:MM (czas warszawski); domyślnie teraz")
    parser.add_argument("--dry-run", action="store_true", help="tylko wypisz rekordy")
    parser.add_argument("--wait", action="store_true", help="po wysyłce czekaj, aż tagger zapisze wszystkie")
    parser.add_argument("--reset-sets", action="store_true", help="usuń zapisane zestawy rekomendacji")
    parser.add_argument("--delete", action="store_true", help="usuń wydarzenia demo z tabeli events")
    args = parser.parse_args(argv)

    if args.reset_sets:
        log.info("Usunięto %d zapisanych zestawów rekomendacji", reset_sets(_table("RESULTS_TABLE")))
        return 0
    if args.delete:
        log.info("Usunięto %d wydarzeń demo", delete_demo(_table("EVENTS_TABLE")))
        return 0

    start = _start(args.start)
    records = build(json.loads(DATA.read_text(encoding="utf-8"))["events"], start, now_utc())
    if args.dry_run:
        json.dump(records, sys.stdout, ensure_ascii=False, indent=1)
        print()
        log.info("%d wydarzeń demo (terminy od %s), bez wysyłki", len(records), start.isoformat(timespec="minutes"))
        return 0

    log.info("Wysłano %d wydarzeń demo w %d wiadomościach", len(records), send(records))
    if args.wait:
        return 0 if wait_for([r["id"] for r in records], _table("EVENTS_TABLE")) else 1
    return 0


# --- rekordy ---

def build(events: list[dict], start: datetime, imported_at: str) -> list[dict]:
    records = []
    for e in events:
        slots = sorted(slot(spec, start) for spec in e["when"])
        record = {
            "id": make_id(ORIGIN, e["key"]),
            "source": ORIGIN,
            "kind": "event",
            "title": e["title"],
            "lead": e["lead"],
            "text": "".join(f"<p>{html.escape(p)}</p>" for p in (e["lead"], e.get("about")) if p),
            "url": None,
            "category": [{"id": None, "name": c} for c in e.get("category", [])],
            "audience": [],
            "district": e.get("district"),
            "online": bool(e.get("online")),
            "venue": e["venue"],
            "location": e.get("location"),
            "occurrences": [{"start": s.isoformat(), "end": f.isoformat(), "allDay": False} for s, f in slots],
            "schedule": [],
            "imageUrl": IMAGE_URL.format(e["image"]) if e.get("image") else None,
            "attributes": {"price": _price(e.get("price")), "ticketUrl": None},
            # Organizator zamiast "dane.um.warszawa.pl" w polu "Źródło" na stronie szczegółów
            "partnerName": e.get("organizer"),
            # Tagger nadpisuje tagi modelu wartościami zadeklarowanymi (parser.apply_declared)
            "declared": e["tags"],
        }
        finalize(record, imported_at)
        record["origin"] = ORIGIN  # finalize ustawia origin importera
        record["contentHash"] = content_hash(record)
        records.append(record)
    return records


def slot(spec: dict, start: datetime) -> tuple[datetime, datetime]:
    """Termin z demo_events.json -> (początek, koniec) w czasie warszawskim."""
    if "in_hours" in spec:  # dziś, względem początku prezentacji (od pełnej albo wpół do)
        base = start.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=30 if start.minute <= 30 else 60)
        begins = base + timedelta(hours=spec["in_hours"])
        return begins, begins + timedelta(minutes=spec["minutes"])
    if "from_day" in spec:  # wydarzenie wielodniowe (wystawa): od..do
        first = _at(start.date() + timedelta(days=spec["from_day"]), spec["time"])
        return first, _at(start.date() + timedelta(days=spec["to_day"]), spec["end"])
    if "weekday" in spec:  # najbliższy taki dzień tygodnia, który jeszcze się nie zaczął
        day = start.date() + timedelta(days=(DAYS.index(spec["weekday"]) - start.weekday()) % 7)
        begins = _at(day, spec["time"])
        if begins <= start:
            begins += timedelta(days=7)
    else:
        begins = _at(start.date() + timedelta(days=spec["day"]), spec["time"])
    return begins, begins + timedelta(minutes=spec["minutes"])


def _at(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=WARSAW)


def _price(price: dict | None) -> dict | None:
    if not price:
        return None
    return {"min": price.get("min"), "max": price.get("max"), "currency": "PLN"}


def _start(value: str | None) -> datetime:
    if not value:
        return datetime.now(WARSAW)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=WARSAW)


# --- AWS ---

def _aws(service: str, kind: str = "client"):
    import boto3  # dopiero tutaj: --dry-run działa bez boto3

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return getattr(boto3, kind)(service, region_name=region)


def _table(env: str):
    if not os.environ.get(env):
        sys.exit(f"Brak zmiennej {env} (uruchom przez scripts/demo-events.sh)")
    return _aws("dynamodb", "resource").Table(os.environ[env])


def send(records: list[dict]) -> int:
    """Paczki po RECORDS_PER_MESSAGE rekordów (JSON array, kontrakt taggera), po 10 wiadomości."""
    queue = os.environ.get("SQS_QUEUE_URL") or sys.exit("Brak zmiennej SQS_QUEUE_URL")
    bodies = [json.dumps(records[i:i + RECORDS_PER_MESSAGE], ensure_ascii=False)
              for i in range(0, len(records), RECORDS_PER_MESSAGE)]
    sqs = _aws("sqs")
    for i in range(0, len(bodies), 10):
        entries = [{"Id": str(n), "MessageBody": body} for n, body in enumerate(bodies[i:i + 10])]
        resp = sqs.send_message_batch(QueueUrl=queue, Entries=entries)
        if resp.get("Failed"):
            raise RuntimeError(f"SQS odrzuciło {len(resp['Failed'])} wiadomości: {resp['Failed'][:2]}")
    return len(bodies)


def wait_for(ids: list[str], table, timeout: int = WAIT_SECONDS) -> bool:
    """Czeka, aż tagger zapisze wszystkie rekordy (dispatcher uruchamia go co minutę)."""
    started, missing = clock.monotonic(), set(ids)
    while clock.monotonic() - started < timeout:
        missing = {i for i in missing if "Item" not in table.get_item(Key={"id": i}, ProjectionExpression="id")}
        if not missing:
            log.info("Tagger zapisał wszystkie %d wydarzeń (%.0f s)", len(ids), clock.monotonic() - started)
            return True
        log.info("Czekam na tagger: %d/%d zapisanych", len(ids) - len(missing), len(ids))
        clock.sleep(15)
    log.error("Po %d s brakuje %d wydarzeń - sprawdź logi taggera: aws logs tail /ecs/codzis-worker", timeout, len(missing))
    return False


def delete_demo(table) -> int:
    """Wydarzenia demo z tabeli events (po prezentacji; potem przebudowa indeksu)."""
    ids, kwargs = [], {"ProjectionExpression": "id, origin"}
    while True:
        page = table.scan(**kwargs)
        ids += [item["id"] for item in page["Items"] if item.get("origin") == ORIGIN]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    with table.batch_writer() as batch:
        for event_id in ids:
            batch.delete_item(Key={"id": event_id})
    return len(ids)


def reset_sets(table) -> int:
    """Zapisane zestawy liczone są tylko po zmianie profilu albo po 12 h - po dodaniu (usunięciu)
    wydarzeń demo usuwamy je, żeby przy najbliższym wejściu policzyły się od nowa."""
    keys, kwargs = [], {"ProjectionExpression": "userId, setKey"}
    while True:
        page = table.scan(**kwargs)
        keys += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    with table.batch_writer() as batch:
        for key in keys:
            batch.delete_item(Key={"userId": key["userId"], "setKey": key["setKey"]})
    return len(keys)


if __name__ == "__main__":
    sys.exit(main())
