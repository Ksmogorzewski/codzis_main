import json

import boto3
import pytest
from moto import mock_aws

from tests.support import API_DIR, DISTRICTS, load_lambda

SUBMISSIONS_TABLE = "test-submissions"
PARTNERS_TABLE = "test-partners"
PAYMENTS_TABLE = "test-payments"
QUEUE_NAME = "test-events"
PARTNER_KEY = "key-1"
PARTNER_NAME = "Teatr Testowy"
STARTER_CREDITS = 2
CATEGORIES = ["Kultura", "Sport", "Rekreacja", "Edukacja", "Dla dzieci"]
CREDIT_PACKAGES = {
    "starter": {"name": "Start", "credits": 1, "price": 19},
    "standard": {"name": "Standard", "credits": 5, "price": 79.99},
}


def _table(name, key, with_partner_index):
    attributes = [{"AttributeName": key, "AttributeType": "S"}]
    extra = {}
    if with_partner_index:
        attributes += [
            {"AttributeName": "partnerId", "AttributeType": "S"},
            {"AttributeName": "createdAt", "AttributeType": "S"},
        ]
        extra["GlobalSecondaryIndexes"] = [
            {
                "IndexName": "byPartner",
                "KeySchema": [
                    {"AttributeName": "partnerId", "KeyType": "HASH"},
                    {"AttributeName": "createdAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ]
    boto3.resource("dynamodb").create_table(
        TableName=name,
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
        AttributeDefinitions=attributes,
        BillingMode="PAY_PER_REQUEST",
        **extra,
    )


@pytest.fixture
def partner_api(monkeypatch):
    """Świeży moduł src/api/handler.py na atrapach DynamoDB i SQS (moto).

    Presigned POST do S3 to tylko podpis po stronie klienta (bez wywołania AWS), więc bucket nie jest potrzebny."""
    with mock_aws():
        _table(SUBMISSIONS_TABLE, "id", with_partner_index=True)
        _table(PARTNERS_TABLE, "partnerId", with_partner_index=False)
        _table(PAYMENTS_TABLE, "id", with_partner_index=True)
        queue_url = boto3.client("sqs").create_queue(QueueName=QUEUE_NAME)["QueueUrl"]

        env = {
            "SUBMISSIONS_TABLE": SUBMISSIONS_TABLE,
            "PARTNERS_TABLE": PARTNERS_TABLE,
            "PAYMENTS_TABLE": PAYMENTS_TABLE,
            "EVENTS_QUEUE_URL": queue_url,
            "PHOTOS_BUCKET": "test-photos",
            "MAX_PHOTO_BYTES": str(5 * 1024 * 1024),
            "EVENT_COST_CREDITS": "1",
            "STARTER_CREDITS": str(STARTER_CREDITS),
            "CREDIT_PACKAGES": json.dumps(CREDIT_PACKAGES),
            "CURRENCY": "PLN",
            "CATEGORIES": json.dumps(CATEGORIES, ensure_ascii=False),
            "DISTRICTS": json.dumps(DISTRICTS, ensure_ascii=False),
            "PUBLIC_BASE_URL": "https://partner.example.com",
            "PARTNERS": json.dumps({PARTNER_KEY: PARTNER_NAME}, ensure_ascii=False),
        }
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        yield load_lambda(API_DIR)


@pytest.fixture
def aws(partner_api):
    """Dostęp do atrap: tabele i kolejka (do sprawdzania efektów ubocznych)."""
    dynamodb = boto3.resource("dynamodb")

    class Aws:
        submissions = dynamodb.Table(SUBMISSIONS_TABLE)
        partners = dynamodb.Table(PARTNERS_TABLE)
        payments = dynamodb.Table(PAYMENTS_TABLE)
        sqs = boto3.client("sqs")
        queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]

        def credits(self, partner_id=PARTNER_KEY):
            return self.partners.get_item(Key={"partnerId": partner_id}).get("Item", {}).get("credits")

        def messages(self):
            response = self.sqs.receive_message(QueueUrl=self.queue_url, MaxNumberOfMessages=10)
            return [json.loads(m["Body"]) for m in response.get("Messages", [])]

    return Aws()


def rest_event(method, path, body=None, api_key=PARTNER_KEY):
    """Zdarzenie REST API (v1, proxy {proxy+}) z kluczem API partnera."""
    event = {
        "httpMethod": method,
        "pathParameters": {"proxy": path} if path else None,
        "requestContext": {"identity": {"apiKeyId": api_key}},
    }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return event


def call(module, method, path, body=None, api_key=PARTNER_KEY):
    """Wywołuje handler i zwraca (status, sparsowane body)."""
    response = module.handler(rest_event(method, path, body, api_key), None)
    assert response["headers"] == {"Content-Type": "application/json"}
    return response["statusCode"], json.loads(response["body"])
