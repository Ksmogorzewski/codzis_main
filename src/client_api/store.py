"""DynamoDB dla Eksploruj, zapisów i Popularnych (klienty tworzone raz, przeżywają między wywołaniami).

Tabele (infra/community.tf), jedyny zapisujący: client-api (+ scripts/seed_demo.py, tylko rekordy seed):

    attendance   PK eventId, SK userId; name (imię z tokenu, bez niego displayName z users, w chwili zapisu - kopia,
                 ustawiana tylko w save()), savedAt (ISO UTC), seed?: true.
                 GSI byUser (userId, savedAt; KEYS_ONLY) - "na co się zapisałem".
    event-stats  PK eventId; saves (licznik, ADD), kind = "event" (stała pod GSI).
                 GSI bySaves (kind, saves; KEYS_ONLY) - top wydarzeń po liczbie zapisanych.

Zapis i wypisanie to jedna transakcja (wiersz w attendance + licznik), więc licznik zgadza się
z listą zapisanych. Wydarzenia (codzis-events, właściciel: tagger) tylko czytamy.
"""

import os
import time
from collections.abc import Iterable
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from codzis_common.http import ApiError
from events import EventCache

EVENTS_TABLE = os.environ["EVENTS_TABLE"]
ATTENDANCE_TABLE = os.environ["ATTENDANCE_TABLE"]
STATS_TABLE = os.environ["STATS_TABLE"]

STATS_KIND = "event"
MAX_ATTENDEES = 100
POPULAR_FETCH = 200  # zapas z indeksu bySaves (część wydarzeń jest poza oknem albo wygasła)
BATCH_GET_MAX = 100  # limit BatchGetItem

# Pola rekordu v1 potrzebne do kart (bez długiego `text`) - mniej danych w pamięci kontenera
CARD_FIELDS = [
    "id", "title", "lead", "url", "imageUrl", "origin", "source", "kind", "partnerName", "district",
    "venue", "location", "online", "occurrences", "schedule", "attributes", "tags", "importedAt",
]  # fmt: skip

dynamodb = boto3.resource("dynamodb")
events_table = dynamodb.Table(EVENTS_TABLE)
attendance_table = dynamodb.Table(ATTENDANCE_TABLE)
stats_table = dynamodb.Table(STATS_TABLE)
# Klient zasobu (nie boto3.client) - transakcje i batch przyjmują zwykłe typy Pythona.
ddb = dynamodb.meta.client


# --------------------------------------------------------------------------- wydarzenia


def scan_events() -> dict[str, dict]:
    """Cała tabela codzis-events (pola kart). Wołane tylko przez EventCache - patrz jej docstring."""
    names = {f"#f{i}": field for i, field in enumerate(CARD_FIELDS)}
    params: dict[str, Any] = {"ProjectionExpression": ", ".join(names), "ExpressionAttributeNames": names}
    found: dict[str, dict] = {}
    while True:
        page = events_table.scan(**params)
        for item in page.get("Items", []):
            found[item["id"]] = item
        if "LastEvaluatedKey" not in page:
            return found
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]


_events_cache = EventCache(scan_events)


def all_events() -> dict[str, dict]:
    """id -> rekord v1 (bez `text`), z pamięci kontenera (maks. 5 min)."""
    return _events_cache.get()


def get_event(event_id: str) -> dict | None:
    """Pełny rekord (z `text`) prosto z tabeli - szczegóły zawsze świeże."""
    return events_table.get_item(Key={"id": event_id}).get("Item")


# --------------------------------------------------------------------------- liczniki


def saves_for(event_ids: Iterable[str]) -> dict[str, int]:
    """Liczba zapisanych dla wielu wydarzeń naraz (BatchGetItem); brak rekordu = 0."""
    ids = list(dict.fromkeys(event_ids))
    counts = dict.fromkeys(ids, 0)
    for i in range(0, len(ids), BATCH_GET_MAX):
        request: dict[str, Any] = {
            STATS_TABLE: {
                "Keys": [{"eventId": e} for e in ids[i : i + BATCH_GET_MAX]],
                "ProjectionExpression": "eventId, saves",
            }
        }
        for attempt in range(5):
            result = ddb.batch_get_item(RequestItems=request)
            for item in result.get("Responses", {}).get(STATS_TABLE, []):
                counts[item["eventId"]] = _count(item.get("saves"))
            request = result.get("UnprocessedKeys") or {}
            if not request:
                break
            time.sleep(0.05 * 2**attempt)
    return counts


def saves_of(event_id: str) -> int:
    item = stats_table.get_item(Key={"eventId": event_id}, ConsistentRead=True).get("Item") or {}
    return _count(item.get("saves"))


def top_saved(limit: int = POPULAR_FETCH) -> list[str]:
    """Id wydarzeń z największą liczbą zapisanych (saves > 0), malejąco (GSI bySaves)."""
    items = stats_table.query(
        IndexName="bySaves",
        KeyConditionExpression=Key("kind").eq(STATS_KIND) & Key("saves").gt(0),
        ScanIndexForward=False,
        Limit=limit,
    )["Items"]
    return [item["eventId"] for item in items]


# --------------------------------------------------------------------------- zapisy


def saved_ids(user_id: str) -> set[str]:
    """Wydarzenia, na które użytkownik jest zapisany (GSI byUser)."""
    params: dict[str, Any] = {"IndexName": "byUser", "KeyConditionExpression": Key("userId").eq(user_id)}
    found: set[str] = set()
    while True:
        page = attendance_table.query(**params)
        found.update(item["eventId"] for item in page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return found
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def is_saved(event_id: str, user_id: str) -> bool:
    key = {"eventId": event_id, "userId": user_id}
    return "Item" in attendance_table.get_item(Key=key, ProjectionExpression="userId", ConsistentRead=True)


def save(event_id: str, user_id: str, name: str | None, saved_at: str) -> bool:
    """Zapis: wiersz w attendance + licznik +1, atomowo. Już zapisany -> False (bez zmian)."""
    item = {"eventId": event_id, "userId": user_id, "savedAt": saved_at}
    if name:
        item["name"] = name
    put = {"Put": {"TableName": ATTENDANCE_TABLE, "Item": item, "ConditionExpression": "attribute_not_exists(userId)"}}
    return _transact([put, _counter(event_id, +1)])


def unsave(event_id: str, user_id: str) -> bool:
    """Wypisanie: usunięcie wiersza + licznik -1, atomowo. Nie był zapisany -> False (bez zmian)."""
    delete = {
        "Delete": {
            "TableName": ATTENDANCE_TABLE,
            "Key": {"eventId": event_id, "userId": user_id},
            "ConditionExpression": "attribute_exists(userId)",
        }
    }
    return _transact([delete, _counter(event_id, -1)])


def attendees(event_id: str) -> list[dict]:
    """Zapisani na wydarzenie, najnowsi najpierw, maks. MAX_ATTENDEES: [{userId, name?, savedAt}].

    Klucz sortowania to userId, więc sortujemy po savedAt w Pythonie (czytamy wszystkie wiersze
    wydarzenia - przy obecnej skali to jedna strona zapytania)."""
    params: dict[str, Any] = {
        "KeyConditionExpression": Key("eventId").eq(event_id),
        "ProjectionExpression": "userId, #name, savedAt",
        "ExpressionAttributeNames": {"#name": "name"},
        "ConsistentRead": True,  # front odświeża listę zaraz po zapisie - własny wpis musi już być
    }
    rows: list[dict] = []
    while True:
        page = attendance_table.query(**params)
        rows.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    rows.sort(key=lambda r: str(r.get("savedAt") or ""), reverse=True)
    return rows[:MAX_ATTENDEES]


def _counter(event_id: str, delta: int) -> dict:
    return {
        "Update": {
            "TableName": STATS_TABLE,
            "Key": {"eventId": event_id},
            "UpdateExpression": "ADD saves :delta SET #kind = :kind",
            "ExpressionAttributeNames": {"#kind": "kind"},
            "ExpressionAttributeValues": {":delta": delta, ":kind": STATS_KIND},
        }
    }


def _transact(items: list[dict]) -> bool:
    """True = zapisano; False = warunek niespełniony (stan już taki, jak chciał użytkownik)."""
    try:
        ddb.transact_write_items(TransactItems=items)
        return True
    except ddb.exceptions.TransactionCanceledException as e:
        reasons = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
        if "ConditionalCheckFailed" in reasons:
            return False
        raise ApiError(409, "Konflikt zapisu, spróbuj ponownie") from e


def _count(value: Any) -> int:
    return max(int(value or 0), 0)
