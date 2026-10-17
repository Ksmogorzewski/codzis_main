#!/usr/bin/env python3
"""Dane testowe na demo: sztuczne zapisy na prawdziwe wydarzenia z najbliższego tygodnia
(dziś + 6 dni, tak samo jak „Popularne” w API).

Zapisuje WYŁĄCZNIE do `codzis-attendance` i `codzis-event-stats` (rekordy z `seed: true`,
userId `seed-001`...). Nie dotyka `codzis-users` ani Cognito. `codzis-events` tylko czyta (scan).

Przykłady (region eu-central-1):
    python scripts/seed_demo.py --dry-run --profile default     # plan, nic nie zapisuje (domyślnie)
    python scripts/seed_demo.py --apply --profile default       # zapis (idempotentny)
    python scripts/seed_demo.py --apply --users 80 --seed-value 7
    python scripts/seed_demo.py --dry-run --week 2026-10-19     # 7 dni od tej daty
    python scripts/seed_demo.py --delete --profile default      # usuwa tylko rekordy seed, koryguje liczniki

Wydarzenia: kind=event z terminem nakładającym się na okno 7 dni (czas warszawski)
albo kind=recurring z niepustym `schedule` (liczy się w każdym tygodniu). Rozkład zapisów jest
w stylu Zipfa (kilka wyraźnie popularnych, długi ogon), każda osoba zapisuje się na 1-5 wydarzeń.
Losowanie jest deterministyczne dla danego `--seed-value`.

Zapis działa jak API: transakcja = Put attendance z `attribute_not_exists(userId)` +
Update stats `ADD saves :one SET kind = :kind`. Ponowne `--apply` niczego nie dodaje.
Tylko biblioteka standardowa + boto3.
"""

import argparse
import random
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError

WARSAW = ZoneInfo("Europe/Warsaw")
REGION = "eu-central-1"
SEED_PREFIX = "seed-"
DEFAULT_SEED_VALUE = 20261018
ZIPF_EXPONENT = 1.1
MAX_SAVES_PER_USER = 5

FIRST_NAMES = [
    "Anna", "Piotr", "Katarzyna", "Marcin", "Magdalena", "Tomasz", "Agnieszka", "Michał", "Barbara", "Paweł",
    "Ewa", "Krzysztof", "Małgorzata", "Jakub", "Joanna", "Marek", "Monika", "Łukasz", "Aleksandra", "Adam",
    "Karolina", "Rafał", "Natalia", "Jan", "Dorota", "Maciej", "Zofia", "Grzegorz", "Julia", "Andrzej",
    "Maria", "Wojciech", "Olga", "Mateusz", "Iwona", "Bartosz", "Beata", "Kamil", "Justyna", "Damian",
    "Weronika", "Sebastian", "Patrycja", "Filip", "Paulina", "Dawid", "Hanna", "Szymon", "Marta", "Kacper",
    "Alicja", "Robert", "Elżbieta", "Dominik", "Sylwia", "Artur", "Izabela", "Norbert", "Lidia", "Stefan",
]  # fmt: skip


# --- Wybór wydarzeń -----------------------------------------------------------------------------


def week_bounds(day: date) -> tuple[datetime, datetime]:
    """Okno 7 dni jak w `GET /api/popular`: `day` 00:00 (włącznie) do `day` + 7 dni 00:00 (wyłącznie)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=WARSAW)
    return start, datetime.combine(day + timedelta(days=7), datetime.min.time(), tzinfo=WARSAW)


def in_week(event: dict, week: tuple[datetime, datetime]) -> bool:
    start, end = week
    if event.get("kind") == "recurring":
        return bool(event.get("schedule"))
    if event.get("kind") != "event":
        return False
    for occ in event.get("occurrences") or []:
        try:
            occ_start = datetime.fromisoformat(occ["start"])
            occ_end = datetime.fromisoformat(occ["end"]) if occ.get("end") else occ_start
        except (KeyError, ValueError):
            continue
        if occ_start < end and occ_end >= start:
            return True
    return False


def scan_all(table, **kwargs) -> list[dict]:
    items: list[dict] = []
    while True:
        page = table.scan(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def pick_events(events_table, week: tuple[datetime, datetime]) -> list[dict]:
    """Wydarzenia z terminem w tygodniu, posortowane po id (stabilna kolejność)."""
    items = scan_all(
        events_table,
        ProjectionExpression="id, title, kind, occurrences, schedule",
    )
    return sorted((e for e in items if in_week(e, week)), key=lambda e: e["id"])


# --- Plan (czysta logika, deterministyczna) -----------------------------------------------------


def user_id(n: int) -> str:
    return f"{SEED_PREFIX}{n:03d}"


def user_name(n: int) -> str:
    return FIRST_NAMES[(n - 1) % len(FIRST_NAMES)]


def build_plan(events: list[dict], users: int, seed_value: int, week_start: datetime) -> list[dict]:
    """Lista zapisów: {eventId, userId, name, savedAt}. Ten sam wynik dla tych samych danych wejściowych."""
    if not events:
        return []
    rng = random.Random(seed_value)
    order = list(events)
    rng.shuffle(order)  # które wydarzenia będą popularne, zależy od ziarna
    weights = [1 / (rank + 1) ** ZIPF_EXPONENT for rank in range(len(order))]
    plan = []
    for n in range(1, users + 1):
        wanted = min(rng.randint(1, MAX_SAVES_PER_USER), len(order))
        chosen: dict[str, dict] = {}
        while len(chosen) < wanted:
            event = rng.choices(order, weights)[0]
            chosen[event["id"]] = event
        for event_id in sorted(chosen):
            saved = week_start - timedelta(minutes=rng.randint(0, 96 * 60))
            plan.append(
                {
                    "eventId": event_id,
                    "userId": user_id(n),
                    "name": user_name(n),
                    "savedAt": saved.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
    return plan


def print_plan(events: list[dict], plan: list[dict], users: int, week: tuple[datetime, datetime]) -> None:
    counts = Counter(p["eventId"] for p in plan)
    titles = {e["id"]: str(e.get("title") or "") for e in events}
    print(f"Tydzień: {week[0]:%Y-%m-%d} - {(week[1] - timedelta(days=1)):%Y-%m-%d}")
    print(f"Wydarzeń z terminem w tygodniu: {len(events)}; sztucznych osób: {users}; zapisów: {len(plan)}")
    print(f"Wydarzeń z co najmniej jednym zapisem: {len(counts)}")
    for event_id, saves in counts.most_common():
        title = titles[event_id]
        print(f"  {saves:3d}  {event_id}  {title[:50]}{'…' if len(title) > 50 else ''}")


# --- Zapis i usuwanie ---------------------------------------------------------------------------


def _cancelled_by_condition(error: ClientError) -> bool:
    if error.response["Error"]["Code"] != "TransactionCanceledException":
        return False
    reasons = error.response.get("CancellationReasons") or []
    return any(r.get("Code") == "ConditionalCheckFailed" for r in reasons)


def save_one(client, attendance: str, stats: str, row: dict) -> bool:
    """Zapis jak w API. True = dodano, False = już było."""
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": attendance,
                        "Item": {
                            "eventId": {"S": row["eventId"]},
                            "userId": {"S": row["userId"]},
                            "name": {"S": row["name"]},
                            "savedAt": {"S": row["savedAt"]},
                            "seed": {"BOOL": True},
                        },
                        "ConditionExpression": "attribute_not_exists(userId)",
                    }
                },
                {
                    "Update": {
                        "TableName": stats,
                        "Key": {"eventId": {"S": row["eventId"]}},
                        "UpdateExpression": "ADD saves :one SET #k = :kind",
                        "ExpressionAttributeNames": {"#k": "kind"},
                        "ExpressionAttributeValues": {":one": {"N": "1"}, ":kind": {"S": "event"}},
                    }
                },
            ]
        )
    except ClientError as error:
        if _cancelled_by_condition(error):
            return False
        raise
    return True


def delete_one(client, attendance: str, stats: str, event_id: str, uid: str) -> bool:
    """Odwrotność save_one. True = usunięto, False = rekordu już nie ma."""
    if not uid.startswith(SEED_PREFIX):
        raise ValueError("Odmowa: userId bez prefiksu seed-")
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Delete": {
                        "TableName": attendance,
                        "Key": {"eventId": {"S": event_id}, "userId": {"S": uid}},
                        "ConditionExpression": "attribute_exists(userId) AND seed = :t",
                        "ExpressionAttributeValues": {":t": {"BOOL": True}},
                    }
                },
                {
                    "Update": {
                        "TableName": stats,
                        "Key": {"eventId": {"S": event_id}},
                        "UpdateExpression": "ADD saves :minus",
                        "ExpressionAttributeValues": {":minus": {"N": "-1"}},
                    }
                },
            ]
        )
    except ClientError as error:
        if _cancelled_by_condition(error):
            return False
        raise
    return True


def apply_plan(client, attendance: str, stats: str, plan: list[dict]) -> int:
    return sum(save_one(client, attendance, stats, row) for row in plan)


def delete_seed(dynamodb, client, attendance: str, stats: str) -> int:
    rows = scan_all(
        dynamodb.Table(attendance),
        FilterExpression="seed = :t AND begins_with(userId, :p)",
        ExpressionAttributeValues={":t": True, ":p": SEED_PREFIX},
        ProjectionExpression="eventId, userId",
    )
    return sum(delete_one(client, attendance, stats, r["eventId"], r["userId"]) for r in rows)


# --- CLI ----------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dane testowe WarsawNow (zapisy na wydarzenia).")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="pokaż plan (domyślnie)")
    mode.add_argument("--apply", action="store_true", help="zapisz do DynamoDB")
    mode.add_argument("--delete", action="store_true", help="usuń rekordy seed i popraw liczniki")
    p.add_argument("--users", type=int, default=60, help="liczba sztucznych osób (domyślnie 60)")
    p.add_argument("--seed-value", type=int, default=DEFAULT_SEED_VALUE, help="ziarno losowania")
    p.add_argument("--week", type=date.fromisoformat, default=None, help="pierwszy dzień okna 7 dni (YYYY-MM-DD), domyślnie dziś")
    p.add_argument("--events-table", default="codzis-events")
    p.add_argument("--attendance-table", default="codzis-attendance")
    p.add_argument("--stats-table", default="codzis-event-stats")
    p.add_argument("--region", default=REGION)
    p.add_argument("--profile", default=None, help="profil AWS (opcjonalnie)")
    args = p.parse_args(argv)
    if args.users < 1:
        p.error("--users musi być >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    dynamodb = session.resource("dynamodb")
    client = session.client("dynamodb")

    if args.delete:
        removed = delete_seed(dynamodb, client, args.attendance_table, args.stats_table)
        print(f"Usunięto rekordów seed: {removed}")
        return 0

    week = week_bounds(args.week or datetime.now(WARSAW).date())
    events = pick_events(dynamodb.Table(args.events_table), week)
    plan = build_plan(events, args.users, args.seed_value, week[0])
    print_plan(events, plan, args.users, week)
    if not events:
        print("Brak wydarzeń w tym tygodniu - nic do zapisania.")
        return 0
    if args.apply:
        added = apply_plan(client, args.attendance_table, args.stats_table, plan)
        print(f"Dodano zapisów: {added} (pominięto istniejące: {len(plan) - added})")
    else:
        print("Dry-run: nic nie zapisano. Użyj --apply, żeby zapisać.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
