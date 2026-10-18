import json
import re
import sys
from urllib.parse import quote

import boto3
import pytest
from moto import mock_aws

from tests.support import CLIENT_API_DIR, DISTRICTS, load_lambda

USERS_TABLE = "test-users"
EVENTS_TABLE = "test-events"
ATTENDANCE_TABLE = "test-attendance"
STATS_TABLE = "test-event-stats"
FRIENDS_TABLE = "test-friends"
CREWS_TABLE = "test-crews"
REQUEST_ID = "req-client-1"
PHOTOS_BUCKET = "test-photos"
PHOTOS_BASE_URL = "https://partner.example.com"


def _create_tables():
    """Tabele jak w infra/client_api.tf i infra/community.tf (klucze i indeksy)."""
    dynamodb = boto3.resource("dynamodb")
    dynamodb.create_table(
        TableName=CREWS_TABLE,
        KeySchema=[{"AttributeName": "eventId", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": "eventId", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.create_table(
        TableName=FRIENDS_TABLE,
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.create_table(
        TableName=USERS_TABLE,
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.create_table(
        TableName=EVENTS_TABLE,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.create_table(
        TableName=ATTENDANCE_TABLE,
        KeySchema=[
            {"AttributeName": "eventId", "KeyType": "HASH"},
            {"AttributeName": "userId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "eventId", "AttributeType": "S"},
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "savedAt", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "byUser",
                "KeySchema": [
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": "savedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamodb.create_table(
        TableName=STATS_TABLE,
        KeySchema=[{"AttributeName": "eventId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "eventId", "AttributeType": "S"},
            {"AttributeName": "kind", "AttributeType": "S"},
            {"AttributeName": "saves", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "bySaves",
                "KeySchema": [
                    {"AttributeName": "kind", "KeyType": "HASH"},
                    {"AttributeName": "saves", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def client_api(monkeypatch):
    """Świeży moduł src/client_api/handler.py na atrapie DynamoDB (moto)."""
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("EVENTS_TABLE", EVENTS_TABLE)
    monkeypatch.setenv("ATTENDANCE_TABLE", ATTENDANCE_TABLE)
    monkeypatch.setenv("STATS_TABLE", STATS_TABLE)
    monkeypatch.setenv("FRIENDS_TABLE", FRIENDS_TABLE)
    monkeypatch.setenv("CREWS_TABLE", CREWS_TABLE)
    monkeypatch.setenv("DISTRICTS", json.dumps(DISTRICTS, ensure_ascii=False))
    monkeypatch.setenv("PHOTOS_BUCKET", PHOTOS_BUCKET)
    monkeypatch.setenv("PHOTOS_BASE_URL", PHOTOS_BASE_URL)
    monkeypatch.delenv("RECOMMENDER_FUNCTION", raising=False)
    with mock_aws():
        _create_tables()
        boto3.client("s3").create_bucket(
            Bucket=PHOTOS_BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-central-1"}
        )
        yield load_lambda(CLIENT_API_DIR)


@pytest.fixture
def users_table(client_api):
    return boto3.resource("dynamodb").Table(USERS_TABLE)


@pytest.fixture
def events_table(client_api):
    return boto3.resource("dynamodb").Table(EVENTS_TABLE)


@pytest.fixture
def attendance_table(client_api):
    return boto3.resource("dynamodb").Table(ATTENDANCE_TABLE)


@pytest.fixture
def stats_table(client_api):
    return boto3.resource("dynamodb").Table(STATS_TABLE)


@pytest.fixture
def friends_table(client_api):
    return boto3.resource("dynamodb").Table(FRIENDS_TABLE)


@pytest.fixture
def crews_table(client_api):
    return boto3.resource("dynamodb").Table(CREWS_TABLE)


@pytest.fixture
def crews(client_api):
    """Moduł src/client_api/crews.py na tej samej atrapie DynamoDB co handler."""
    return sys.modules.get("crews") or load_lambda(CLIENT_API_DIR, "crews")


@pytest.fixture
def friends(client_api):
    """Moduł src/client_api/friends.py na tej samej atrapie DynamoDB co handler."""
    return sys.modules.get("friends") or load_lambda(CLIENT_API_DIR, "friends")


def api_event(route_key, body=None, claims=None, path=None, query=None):
    """Zdarzenie HTTP API (payload 2.0) po autoryzacji JWT, jak z API Gateway.

    `route_key` jak w infra/client_api.tf ("GET /api/events/{id}"). rawPath to szablon z wartościami z `path`
    zakodowanymi jak w adresie URL (każda w jednym segmencie) - po nim trasę wybiera router Powertools."""
    method, template = route_key.split(" ", 1)
    raw_path = re.sub(r"\{(\w+)\}", lambda m: quote((path or {}).get(m.group(1), ""), safe=""), template)
    event = {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": raw_path,
        "headers": {},
        "requestContext": {
            "authorizer": {"jwt": {"claims": claims or {"sub": "user-1", "email": "ala@example.com"}}},
            "http": {"method": method, "path": raw_path},
            "requestId": REQUEST_ID,
            "stage": "$default",
        },
    }
    if path is not None:
        event["pathParameters"] = path
    if query is not None:
        event["queryStringParameters"] = query
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return event


def call(module, route_key, body=None, claims=None, path=None, query=None):
    """Wywołuje handler i zwraca (status, sparsowane body)."""
    response = module.handler(api_event(route_key, body, claims, path, query), None)
    assert response["headers"] == {"Content-Type": "application/json"}
    return response["statusCode"], json.loads(response["body"])
