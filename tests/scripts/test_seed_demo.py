import importlib.util
from collections import Counter
from datetime import date
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

SPEC = importlib.util.spec_from_file_location(
    "seed_demo", Path(__file__).resolve().parents[2] / "scripts" / "seed_demo.py"
)
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)

EVENTS, ATTENDANCE, STATS = "t-events", "t-attendance", "t-stats"
WEEK_DAY = date(2026, 10, 21)  # tydzień 19-25.10.2026


def make_event(event_id, start, end=None):
    occ = {"start": start, "allDay": False}
    if end:
        occ["end"] = end
    return {"id": event_id, "title": f"Wydarzenie {event_id}", "kind": "event", "occurrences": [occ]}


ITEMS = [
    make_event("in-1", "2026-10-20T18:00:00+02:00"),
    make_event("in-2", "2026-10-25T23:00:00+01:00", "2026-10-26T01:00:00+01:00"),
    make_event("overlap", "2026-10-18T10:00:00+02:00", "2026-10-19T12:00:00+02:00"),
    make_event("before", "2026-10-10T18:00:00+02:00"),
    make_event("after", "2026-10-26T00:30:00+01:00"),
    {"id": "rec-1", "title": "Joga", "kind": "recurring", "schedule": [{"day": "monday", "start": "18:00"}]},
    {"id": "rec-empty", "title": "Brak", "kind": "recurring", "schedule": []},
]


@pytest.fixture
def aws():
    with mock_aws():
        db = boto3.resource("dynamodb", region_name="eu-central-1")
        for name, keys in [
            (EVENTS, [("id", "HASH")]),
            (ATTENDANCE, [("eventId", "HASH"), ("userId", "RANGE")]),
            (STATS, [("eventId", "HASH")]),
        ]:
            db.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": a, "KeyType": t} for a, t in keys],
                AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a, _ in keys],
                BillingMode="PAY_PER_REQUEST",
            )
        for item in ITEMS:
            db.Table(EVENTS).put_item(Item=item)
        yield db, boto3.client("dynamodb", region_name="eu-central-1")


def run(*extra):
    args = ["--events-table", EVENTS, "--attendance-table", ATTENDANCE, "--stats-table", STATS]
    return seed.main([*args, "--week", WEEK_DAY.isoformat(), *extra])


def counts(db):
    att = Counter(i["eventId"] for i in seed.scan_all(db.Table(ATTENDANCE)))
    stats = {i["eventId"]: int(i["saves"]) for i in seed.scan_all(db.Table(STATS))}
    return att, stats


def test_selection_only_week_and_recurring(aws):
    db, _ = aws
    week = seed.week_bounds(WEEK_DAY)
    ids = [e["id"] for e in seed.pick_events(db.Table(EVENTS), week)]
    assert ids == ["in-1", "in-2", "overlap", "rec-1"]


def test_plan_deterministic_and_bounded(aws):
    db, _ = aws
    week = seed.week_bounds(WEEK_DAY)
    events = seed.pick_events(db.Table(EVENTS), week)
    a = seed.build_plan(events, 60, 1, week[0])
    assert a == seed.build_plan(events, 60, 1, week[0])
    assert a != seed.build_plan(events, 60, 2, week[0])
    per_user = Counter(p["userId"] for p in a)
    assert len(per_user) == 60 and all(1 <= n <= 4 for n in per_user.values())  # 4 wydarzenia w puli
    assert {p["eventId"] for p in a} <= {"in-1", "in-2", "overlap", "rec-1"}


def test_dry_run_writes_nothing(aws, capsys):
    db, _ = aws
    assert run("--dry-run") == 0
    assert "Dry-run" in capsys.readouterr().out
    assert counts(db) == (Counter(), {})


def test_apply_stats_match_and_idempotent(aws):
    db, _ = aws
    run("--apply", "--users", "30")
    att, stats = counts(db)
    assert sum(att.values()) > 0 and att == Counter(stats)
    rows = seed.scan_all(db.Table(ATTENDANCE))
    assert all(r["seed"] is True and r["userId"].startswith("seed-") for r in rows)
    assert {i["kind"] for i in seed.scan_all(db.Table(STATS))} == {"event"}
    run("--apply", "--users", "30")
    assert counts(db) == (att, stats)


def test_delete_only_seed_rows(aws):
    db, _ = aws
    run("--apply", "--users", "30")
    real = {"eventId": "in-1", "userId": "real-user", "name": "Ola", "savedAt": "2026-10-18T10:00:00Z"}
    db.Table(ATTENDANCE).put_item(Item=real)
    db.Table(STATS).update_item(
        Key={"eventId": "in-1"}, UpdateExpression="ADD saves :one", ExpressionAttributeValues={":one": 1}
    )
    before_in1 = counts(db)[1]["in-1"]
    run("--delete")
    att, stats = counts(db)
    assert att == Counter({"in-1": 1})
    assert db.Table(ATTENDANCE).get_item(Key={"eventId": "in-1", "userId": "real-user"})["Item"] == real
    assert stats["in-1"] == 1
    assert before_in1 >= 1
    assert all(v == 0 for k, v in stats.items() if k != "in-1")
