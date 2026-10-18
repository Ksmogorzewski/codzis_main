import importlib.util
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

SPEC = importlib.util.spec_from_file_location(
    "seed_demo", Path(__file__).resolve().parents[2] / "scripts" / "seed_demo.py"
)
assert SPEC and SPEC.loader
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)

EVENTS, ATTENDANCE, STATS = "t-events", "t-attendance", "t-stats"
FRIENDS = "t-friends"
DEMO_EMAIL = "demo@example.com"
WEEK_DAY = date(2026, 10, 19)  # okno 19-25.10.2026


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
        db.create_table(
            TableName=FRIENDS,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        for item in ITEMS:
            db.Table(EVENTS).put_item(Item=item)
        yield db, boto3.client("dynamodb", region_name="eu-central-1")


def run(*extra, cognito=None):
    args = ["--events-table", EVENTS, "--attendance-table", ATTENDANCE, "--stats-table", STATS]
    return seed.main([*args, "--week", WEEK_DAY.isoformat(), *extra], cognito=cognito)


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


# --- znajomi testowi (--friends-of) ---------------------------------------------------------------


class FakeCognito:
    """Minimalny klient Cognito: tylko `list_users` z filtrem `email = "..."` (moto wymaga joserfc)."""

    pool_id = "eu-central-1_TEST"

    def __init__(self, attributes):
        self.attributes = attributes
        self.calls = []

    def list_users(self, **kwargs):
        self.calls.append(kwargs)
        wanted = kwargs["Filter"].removeprefix('email = "').removesuffix('"')
        attrs = [{"Name": k, "Value": v} for k, v in self.attributes.items()]
        return {"Users": [{"Attributes": attrs}] if self.attributes.get("email") == wanted else []}


@pytest.fixture
def cognito():
    return FakeCognito({"sub": "demo-sub-1", "email": DEMO_EMAIL, "name": "Dawid"})


def demo_sub(cognito):
    return seed.lookup_user(cognito, cognito.pool_id, DEMO_EMAIL)[0]


def run_friends(cognito, *extra):
    return run(
        "--friends-table", FRIENDS, "--friends-of", DEMO_EMAIL, "--user-pool-id", cognito.pool_id, *extra,
        cognito=cognito,
    )  # fmt: skip


def friend_rows(db):
    return sorted(seed.scan_all(db.Table(FRIENDS)), key=lambda r: (r["userId"], r["sk"]))


def test_friends_of_creates_mutual_seed_friendships(aws, cognito):
    db, _ = aws
    sub = demo_sub(cognito)
    run_friends(cognito, "--apply", "--users", "1")  # plan nie daje znajomym zapisów: muszą zostać dopisane
    rows = friend_rows(db)
    assert len(rows) == 6 and all(r["seed"] is True for r in rows)
    mine = {r["sk"]: r for r in rows if r["userId"] == sub}
    assert set(mine) == {f"friend#seed-00{n}" for n in (1, 2, 3)}
    for n in (1, 2, 3):
        assert mine[f"friend#seed-00{n}"]["name"] == seed.user_name(n)
        theirs = db.Table(FRIENDS).get_item(Key={"userId": f"seed-00{n}", "sk": f"friend#{sub}"})["Item"]
        assert theirs["name"] == "Dawid" and theirs["since"] == mine[f"friend#seed-00{n}"]["since"]
        assert theirs["since"].endswith("Z")
    att = seed.scan_all(db.Table(ATTENDANCE))
    window_ids = {"in-1", "in-2", "overlap", "rec-1"}
    for n in (1, 2, 3):
        assert any(a["userId"] == f"seed-00{n}" and a["eventId"] in window_ids for a in att)


def test_friends_of_name_fallback_ty(aws, cognito):
    db, _ = aws
    del cognito.attributes["name"]
    run_friends(cognito, "--apply")
    assert {r["name"] for r in friend_rows(db) if r["userId"].startswith("seed-")} == {"Ty"}


def test_friends_of_idempotent(aws, cognito):
    db, _ = aws
    run_friends(cognito, "--apply")
    first = friend_rows(db), counts(db)
    run_friends(cognito, "--apply")
    assert (friend_rows(db), counts(db)) == first


def test_friends_of_dry_run_writes_nothing_and_hides_email(aws, cognito, capsys):
    db, _ = aws
    run_friends(cognito, "--dry-run")
    out = capsys.readouterr().out
    assert DEMO_EMAIL not in out and seed.user_name(1) in out
    assert friend_rows(db) == [] and counts(db) == (Counter(), {})


def test_lookup_user_is_read_only_and_rejects_unknown(cognito):
    assert seed.lookup_sub(cognito, cognito.pool_id, DEMO_EMAIL) == "demo-sub-1"
    assert [set(c) for c in cognito.calls] == [{"UserPoolId", "Filter", "Limit"}]
    with pytest.raises(SystemExit):
        seed.lookup_user(cognito, cognito.pool_id, "inny@example.com")


def test_friends_of_requires_user_pool(aws):
    with pytest.raises(SystemExit):
        run("--friends-of", DEMO_EMAIL, "--friends-table", FRIENDS)


def test_delete_removes_only_seed_friendships(aws, cognito):
    db, _ = aws
    sub = demo_sub(cognito)
    run_friends(cognito, "--apply")
    real = [
        {"userId": sub, "sk": "friend#real-1", "name": "Ola", "since": "2026-10-01T10:00:00Z"},
        {"userId": "real-1", "sk": "friend#" + sub, "name": "Dawid", "since": "2026-10-01T10:00:00Z"},
        {"userId": sub, "sk": "code", "code": "WAW-ABCDEF"},
    ]
    for item in real:
        db.Table(FRIENDS).put_item(Item=item)
    run("--friends-table", FRIENDS, "--delete")
    assert friend_rows(db) == sorted(real, key=lambda r: (r["userId"], r["sk"]))


def test_friend_with_only_past_save_gets_upcoming_save(aws):
    db, client = aws
    events = seed.pick_events(db.Table(EVENTS), seed.week_bounds(WEEK_DAY))
    now = datetime(2026, 10, 20, 20, 0, tzinfo=seed.WARSAW)  # in-1 (18:00) już się zaczęło
    past = {"eventId": "in-1", "userId": "seed-001", "name": seed.user_name(1), "savedAt": "2026-10-19T10:00:00Z"}
    assert seed.save_one(client, ATTENDANCE, STATS, past)
    args = SimpleNamespace(friends_table=FRIENDS, attendance_table=ATTENDANCE, stats_table=STATS)
    seed.apply_friends(db, client, args, events, [], ("demo-sub-1", "Dawid"), now)
    saved = {a["eventId"] for a in seed.scan_all(db.Table(ATTENDANCE)) if a["userId"] == "seed-001"}
    upcoming = {e["id"] for e in events if seed.is_upcoming(e, now)}
    assert upcoming == {"in-2", "rec-1"} and "in-1" in saved and saved & upcoming
