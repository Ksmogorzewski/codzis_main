import json

import boto3
import pytest
from moto import mock_aws

from tests.support import CLIENT_API_DIR, DISTRICTS, load_lambda

USERS_TABLE = "test-users"
EVENTS_TABLE = "test-events"
ATTENDANCE_TABLE = "test-attendance"
STATS_TABLE = "test-event-stats"


def _create_tables():
    """Tabele jak w infra/client_api.tf i infra/community.tf (klucze i indeksy)."""
    dynamodb = boto3.resource("dynamodb")
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
    monkeypatch.setenv("DISTRICTS", json.dumps(DISTRICTS, ensure_ascii=False))
    monkeypatch.delenv("RECOMMENDER_FUNCTION", raising=False)
    with mock_aws():
        _create_tables()
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


def api_event(route_key, body=None, claims=None, path=None, query=None):
    """Zdarzenie HTTP API (payload 2.0) po autoryzacji JWT, jak z API Gateway."""
    event = {
        "routeKey": route_key,
        "requestContext": {
            "authorizer": {"jwt": {"claims": claims or {"sub": "user-1", "email": "ala@example.com"}}},
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
