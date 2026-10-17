import json

import boto3
import pytest
from moto import mock_aws

from tests.support import CLIENT_API_DIR, DISTRICTS, load_lambda

USERS_TABLE = "test-users"


@pytest.fixture
def client_api(monkeypatch):
    """Świeży moduł src/client_api/handler.py na atrapie DynamoDB (moto)."""
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("DISTRICTS", json.dumps(DISTRICTS, ensure_ascii=False))
    monkeypatch.delenv("RECOMMENDER_FUNCTION", raising=False)
    with mock_aws():
        boto3.resource("dynamodb").create_table(
            TableName=USERS_TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield load_lambda(CLIENT_API_DIR)


@pytest.fixture
def users_table(client_api):
    return boto3.resource("dynamodb").Table(USERS_TABLE)


def api_event(route_key, body=None, claims=None):
    """Zdarzenie HTTP API (payload 2.0) po autoryzacji JWT, jak z API Gateway."""
    event = {
        "routeKey": route_key,
        "requestContext": {
            "authorizer": {"jwt": {"claims": claims or {"sub": "user-1", "email": "ala@example.com"}}},
        },
    }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return event


def call(module, route_key, body=None, claims=None):
    """Wywołuje handler i zwraca (status, sparsowane body)."""
    response = module.handler(api_event(route_key, body, claims), None)
    assert response["headers"] == {"Content-Type": "application/json"}
    return response["statusCode"], json.loads(response["body"])
