"""Indeks rekomendacji: wektory eventów + odchudzone rekordy w jednym pliku .npz (S3).

refresh() czyta całą tabelę eventów, liczy embeddingi tylko dla nowych/zmienionych tekstów
(resztę bierze z poprzedniego indeksu) i zapisuje plik, gdy coś się zmieniło. Serwowanie
pobiera plik i co kilka minut sprawdza (ETag), czy nie ma nowszego.

Lokalnie (bez AWS): INDEX_PATH = ścieżka pliku zamiast S3, EVENTS_FILE = JSON z eventami
zamiast skanu DynamoDB.
"""

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
from botocore.exceptions import ClientError

from recommender import DEFAULT_MODEL, EventChunk, VectorIndex, chunk_events
from recommender.retriever import next_slot

log = logging.getLogger(__name__)

# Pola rekordu potrzebne do filtrów, rankingu i kart na stronie (bez HTML-owego "text")
FIELDS = [
    "id", "origin", "source", "kind", "title", "lead", "url", "category", "district", "online",
    "venue", "location", "occurrences", "schedule", "startsAt", "endsAt", "imageUrl",
    "attributes", "tags", "facets", "partnerName",
]


class Index:
    """Zawartość pliku indeksu: eventy + wiersze (chunki) z wektorami i hashami tekstów."""

    def __init__(self, events, chunk_ids, hashes, vectors, meta):
        self.events, self.chunk_ids, self.hashes, self.vectors, self.meta = events, chunk_ids, hashes, vectors, meta

    def vector_index(self) -> VectorIndex:
        index = VectorIndex()
        if self.chunk_ids:
            index.add([EventChunk(event_id=i, event_url="", text="") for i in self.chunk_ids], self.vectors)
        return index

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(
            buf,
            vectors=self.vectors.astype(np.float32),
            chunk_ids=np.array(self.chunk_ids, dtype=str),
            hashes=np.array(self.hashes, dtype=str),
            events=_json_bytes(self.events),
            meta=_json_bytes(self.meta),
        )
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Index":
        with np.load(io.BytesIO(data), allow_pickle=False) as npz:
            return cls(
                events=json.loads(npz["events"].tobytes()),
                chunk_ids=npz["chunk_ids"].tolist(),
                hashes=npz["hashes"].tolist(),
                vectors=npz["vectors"],
                meta=json.loads(npz["meta"].tobytes()),
            )


class S3Store:
    def __init__(self, s3, bucket: str, key: str):
        self.s3, self.bucket, self.key = s3, bucket, key

    def version(self) -> str | None:
        try:
            return self.s3.head_object(Bucket=self.bucket, Key=self.key)["ETag"]
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return None
            raise

    def load(self) -> Index | None:
        try:
            body = self.s3.get_object(Bucket=self.bucket, Key=self.key)["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        return Index.from_bytes(body)

    def save(self, index: Index) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=self.key, Body=index.to_bytes(), ContentType="application/octet-stream")


class FileStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def version(self) -> str | None:
        return str(self.path.stat().st_mtime_ns) if self.path.exists() else None

    def load(self) -> Index | None:
        return Index.from_bytes(self.path.read_bytes()) if self.path.exists() else None

    def save(self, index: Index) -> None:
        self.path.write_bytes(index.to_bytes())


def scan_events(table) -> list[dict]:
    names = {f"#f{i}": f for i, f in enumerate(FIELDS)}  # część pól to słowa zastrzeżone DynamoDB
    kwargs = {"ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names}
    items = []
    while True:
        page = table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return [_plain(item) for item in items]
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def load_events_file(path: str) -> list[dict]:
    return [{k: v for k, v in e.items() if k in FIELDS} for e in json.loads(Path(path).read_text())]


def slim(event: dict, now_iso: str) -> dict | None:
    """Rekord do indeksu albo None, gdy event już się skończył (TTL usuwa go z opóźnieniem)."""
    if not event.get("id") or not event.get("title"):
        return None
    if next_slot(event, now=now_iso) is None:
        return None
    record = {k: event[k] for k in FIELDS if event.get(k) not in (None, "", [], {})}
    if record.get("occurrences"):
        # Tylko terminy, które jeszcze się nie skończyły
        record["occurrences"] = [o for o in record["occurrences"] if next_slot({"occurrences": [o]}, now=now_iso)]
    return record


def text_hash(text: str, model_name: str) -> str:
    return hashlib.sha1(f"{model_name}\n{text}".encode("utf-8")).hexdigest()


def refresh(raw_events: list[dict], previous: Index | None, load_model, model_name: str = DEFAULT_MODEL) -> tuple[Index | None, dict]:
    """-> (nowy indeks albo None, gdy nic się nie zmieniło; statystyki do logów)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    events = sorted(filter(None, (slim(e, now_iso) for e in raw_events)), key=lambda e: e["id"])
    chunks = chunk_events(events)
    hashes = [text_hash(c.text, model_name) for c in chunks]
    digest = hashlib.sha1(_json_bytes([events, hashes]).tobytes()).hexdigest()
    stats = {"events": len(events), "skipped": len(raw_events) - len(events), "chunks": len(chunks), "embedded": 0}

    if previous and previous.meta.get("digest") == digest:
        return None, stats

    cache = {}
    if previous and previous.meta.get("model") == model_name:
        cache = dict(zip(previous.hashes, previous.vectors))
    texts = {h: c.text for h, c in zip(hashes, chunks)}
    missing = [h for h in texts if h not in cache]
    if missing:
        log.info("Embedding %d nowych tekstów", len(missing))
        cache.update(zip(missing, load_model().encode([texts[h] for h in missing])))
        stats["embedded"] = len(missing)

    dim = len(next(iter(cache.values()))) if cache else 0
    vectors = np.stack([cache[h] for h in hashes]) if hashes else np.zeros((0, dim), dtype=np.float32)
    meta = {"model": model_name, "digest": digest, "builtAt": now_iso, "events": len(events), "chunks": len(chunks)}
    return Index(events, [c.event_id for c in chunks], hashes, vectors, meta), stats


def _plain(value):
    """DynamoDB (Decimal, set) -> zwykły JSON."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, set, tuple)):
        return [_plain(v) for v in value]
    return value


def _json_bytes(value) -> np.ndarray:
    return np.frombuffer(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"), dtype=np.uint8)
