import io
import json
import sys
from datetime import UTC, datetime, timedelta

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
REQUEST_ID = "req-partner-1"
CATEGORIES = ["Kultura", "Sport", "Rekreacja", "Edukacja", "Dla dzieci"]
CREDIT_PACKAGES = {
    "starter": {"name": "Start", "credits": 1, "price": 19},
    "standard": {"name": "Standard", "credits": 5, "price": 79.99},
}


# Dane testowe wspólne dla test_handler.py i test_contract.py.
GOOGLE = {"sub": "5f1c2e7a-google", "name": "  Anna   Nowak ", "email": "anna@example.com", "email_verified": "true"}

WARSAW = "+02:00"


def future(days=7, hour=19):
    day = datetime.now(UTC) + timedelta(days=days)
    return f"{day:%Y-%m-%d}T{hour:02d}:00:00{WARSAW}"


def valid_event(**overrides):
    body = {
        "title": "  Koncert w parku ",
        "lead": "Muzyka na żywo",
        "text": "Pierwszy akapit\nz nową linią\n\nDrugi <b>akapit</b>",
        "venue": "Park Skaryszewski",
        "street": "al. Zieleniecka",
        "streetNumber": "1",
        "url": "https://example.com/koncert",
        "cost": "Płatne",
        "registration": "Wymagany bilet",
        "setting": "Na zewnątrz",
        "audience": ["Rodziny / wszystkie grupy", "Dorośli (18-64)", "Dorośli (18-64)"],
        "priceMin": "20",
        "priceMax": 35.5,
        "category": "Kultura",
        "district": "Wola",
        "startsAt": future(hour=19),
        "endsAt": future(hour=21),
        "photoContentType": "image/jpeg",
    }
    body.update(overrides)
    return body


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
        _forget_route_modules()
        yield load_lambda(API_DIR)
        _forget_route_modules()  # następne testy (np. client-api) nie mogą dostać tras partnera


def _forget_route_modules():
    """`routes` to pakiet (katalog), którego `load_lambda` nie czyści, a client-api ma pakiet o tej samej nazwie.
    Bez tego trasy z poprzedniego testu (albo innej Lambdy) zostałyby podpięte do nowej aplikacji."""
    for name in [n for n in sys.modules if n == "routes" or n.startswith("routes.")]:
        del sys.modules[name]


@pytest.fixture
def access_logs(partner_api):
    """Linie logu JSON z Powertools Logger (nie przechodzi przez caplog) jako lista słowników."""
    from codzis_common.app import logger

    stream = io.StringIO()
    previous = logger.registered_handler.setStream(stream)  # type: ignore[attr-defined]
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    logger.registered_handler.setStream(previous)  # type: ignore[attr-defined]


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


def rest_event(method, path, body=None, api_key=PARTNER_KEY, claims=None):
    """Zdarzenie REST API v1 jak z API Gateway za CloudFrontem (zasób /{proxy+}, stage "api") z kluczem API
    partnera albo - z `claims` - z tokenem Google (autoryzator Cognito: claimy w requestContext.authorizer.claims,
    bez klucza API). `path` to adres względem stage'a ("/me"), `requestContext.path` - z prefiksem stage'a."""
    identity = {"apiKeyId": None if claims else api_key, "sourceIp": "203.0.113.10", "userAgent": "Amazon CloudFront"}
    context = {
        "resourcePath": "/{proxy+}",
        "httpMethod": method,
        "path": f"/api/{path}",
        "stage": "api",
        "requestId": REQUEST_ID,
        "identity": identity,
    }
    if claims:
        context["authorizer"] = {"claims": claims}
    headers = {"Content-Type": "application/json", "Host": "abc123.execute-api.eu-central-1.amazonaws.com"}
    event = {
        "resource": "/{proxy+}",
        "path": f"/{path}",
        "httpMethod": method,
        "headers": headers,
        "multiValueHeaders": {name: [value] for name, value in headers.items()},
        "queryStringParameters": None,
        "multiValueQueryStringParameters": None,
        "pathParameters": {"proxy": path} if path else None,
        "stageVariables": None,
        "requestContext": context,
        "body": None,
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return event


def call(module, method, path, body=None, api_key=PARTNER_KEY, claims=None):
    """Wywołuje handler i zwraca (status, sparsowane body)."""
    response = module.handler(rest_event(method, path, body, api_key, claims), None)
    assert response["headers"] == {"Content-Type": "application/json"}
    return response["statusCode"], json.loads(response["body"])
