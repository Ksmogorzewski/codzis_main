"""Importer: jednorazowy task ECS (EventBridge co 2 h).

Dla każdego źródła UM Warszawy:
    1. POST do API (cały zbiór w jednej odpowiedzi, bez paginacji)
    2. surowa odpowiedź -> s3://<bucket>/raw/<source>/<data>/<czas>.json.gz (podgląd / replay)
    3. mapowanie na wspólny schemat (schema.py, sources.py)
    4. diff po contentHash ze stanem z poprzedniego przebiegu (s3://<bucket>/state/<source>.json)
    5. nowe/zmienione rekordy -> SQS jako JSON array (kontrakt taggera), paczki po RECORDS_PER_MESSAGE
    6. zapis nowego stanu - dopiero PO wysłaniu, więc awaria w trakcie = ponowna wysyłka (tagger pomija duplikaty)

Źródła są niezależne: błąd jednego nie blokuje pozostałych. Kod wyjścia 1 = któreś źródło się nie udało.

    python main.py             # pełny import
    python main.py --dry-run   # tylko pobranie + mapowanie, bez S3/SQS (lokalny podgląd)
"""

import argparse
import gzip
import json
import logging
import os
import sys
import time
import urllib.request

import boto3

from schema import finalize, now_utc
from sources import SOURCES

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
DATA_BUCKET = os.environ["DATA_BUCKET"]
RECORDS_PER_MESSAGE = int(os.environ.get("RECORDS_PER_MESSAGE", 20))
MAX_MESSAGE_BYTES = 240_000  # limit SQS 256 KiB z zapasem
HTTP_TIMEOUT_S = int(os.environ.get("HTTP_TIMEOUT_S", 60))
HTTP_RETRIES = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("importer")

# botocore czyta AWS_DEFAULT_REGION, nie AWS_REGION - region podajemy jawnie
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description="Import API UM Warszawy -> SQS")
    args.add_argument("--dry-run", action="store_true", help="bez zapisu do S3 i SQS")
    dry_run = args.parse_args(argv).dry_run

    token = os.environ.get("UM_API_TOKEN", "")
    if not token or token == "CHANGE_ME":
        log.error("UM_API_TOKEN nie jest ustawiony (SSM)")
        return 1

    log.info("Start importu: %s%s", ", ".join(s.name for s in SOURCES), " [dry-run]" if dry_run else "")
    ok = True
    for source in SOURCES:
        try:
            import_source(source, token, dry_run)
        except Exception:
            log.exception("Import %s nie powiódł się", source.name)
            ok = False
    return 0 if ok else 1


def import_source(source, token: str, dry_run: bool = False) -> None:
    started = now_utc()
    log.info("%s: pobieram %s", source.name, source.endpoint)
    raw = fetch(source.endpoint, token)
    if not isinstance(raw, list) or not raw:
        # Pusta odpowiedź to raczej awaria API niż brak danych - nie nadpisujemy stanu
        raise RuntimeError(f"pusta lub nieoczekiwana odpowiedź ({type(raw).__name__})")
    records = [finalize(r, started) for r in source.map_records(raw)]
    if dry_run:
        kinds = {k: sum(1 for r in records if r["kind"] == k) for k in {r["kind"] for r in records}}
        log.info("%s [dry-run]: %d surowych -> %d rekordów %s", source.name, len(raw), len(records), kinds)
        return

    save_raw(source.name, raw, started)
    log.info("%s: zmapowano %d rekordów, porównuję ze stanem z poprzedniego importu", source.name, len(records))
    previous = load_state(source.name)
    changed = [r for r in records if previous.get(r["id"]) != r["contentHash"]]
    new = sum(1 for r in changed if r["id"] not in previous)
    removed = len(set(previous) - {r["id"] for r in records})

    messages = send(changed)
    save_state(source.name, {r["id"]: r["contentHash"] for r in records})
    log.info(
        "%s: %d surowych -> %d rekordów; nowe %d, zmienione %d, usunięte w źródle %d; wysłano %d wiadomości",
        source.name, len(raw), len(records), new, len(changed) - new, removed, messages,
    )


def fetch(url: str, token: str):
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            t0 = time.monotonic()
            request = urllib.request.Request(url, method="POST", data=b"", headers={"Authorization": token})
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
                body = response.read()
            log.info("  HTTP %s, %d KB w %.1f s", response.status, len(body) // 1024, time.monotonic() - t0)
            payload = json.loads(body.decode("utf-8-sig"))  # API zwraca JSON z BOM
            # Część endpointów zwraca gołą listę, część {"result": [...]}
            if isinstance(payload, dict) and isinstance(payload.get("result"), list):
                return payload["result"]
            return payload
        except Exception as e:
            if attempt == HTTP_RETRIES:
                raise
            log.warning("POST %s: próba %d/%d nieudana po %.0f s (%s), ponawiam", url, attempt, HTTP_RETRIES, time.monotonic() - t0, e)
            time.sleep(5 * attempt)


def send(records: list) -> int:
    """Pakuje rekordy w wiadomości (JSON array) i wysyła paczkami po 10. Zwraca liczbę wiadomości."""
    bodies, current = [], []
    for record in records:
        candidate = current + [record]
        if current and (len(candidate) > RECORDS_PER_MESSAGE or len(_dumps(candidate).encode()) > MAX_MESSAGE_BYTES):
            bodies.append(_dumps(current))
            candidate = [record]
        current = candidate
    if current:
        bodies.append(_dumps(current))

    for i in range(0, len(bodies), 10):
        entries = [{"Id": str(n), "MessageBody": body} for n, body in enumerate(bodies[i : i + 10])]
        resp = sqs.send_message_batch(QueueUrl=QUEUE_URL, Entries=entries)
        if resp.get("Failed"):
            raise RuntimeError(f"SQS odrzuciło {len(resp['Failed'])} wiadomości: {resp['Failed'][:2]}")
    return len(bodies)


def save_raw(source: str, raw, started: str) -> None:
    key = f"raw/{source}/{started[:10]}/{started[11:19].replace(':', '')}.json.gz"
    s3.put_object(
        Bucket=DATA_BUCKET, Key=key, ContentType="application/json", ContentEncoding="gzip",
        Body=gzip.compress(_dumps(raw).encode()),
    )


def load_state(source: str) -> dict:
    try:
        obj = s3.get_object(Bucket=DATA_BUCKET, Key=f"state/{source}.json")
    except s3.exceptions.NoSuchKey:
        return {}
    return json.loads(obj["Body"].read())


def save_state(source: str, state: dict) -> None:
    s3.put_object(Bucket=DATA_BUCKET, Key=f"state/{source}.json", ContentType="application/json", Body=_dumps(state).encode())


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    sys.exit(main())
