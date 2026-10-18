"""Klienty AWS (tworzone raz, przeżywają między wywołaniami) i wspólne operacje na DynamoDB."""

from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

from codzis_common.aws import AWS_CONFIG
from codzis_common.http import ApiError
from config import LIST_LIMIT, PARTNERS_TABLE, PAYMENTS_TABLE, REGION, SUBMISSIONS_TABLE

dynamodb = boto3.resource("dynamodb", config=AWS_CONFIG)
submissions_table = dynamodb.Table(SUBMISSIONS_TABLE)
partners_table = dynamodb.Table(PARTNERS_TABLE)
payments_table = dynamodb.Table(PAYMENTS_TABLE)
# Klient zasobu (nie boto3.client) - transakcje przyjmują zwykłe typy Pythona.
ddb = dynamodb.meta.client
sqs = boto3.client("sqs", config=AWS_CONFIG)

# Regionalny endpoint - globalny potrafi zwracać 307 dla świeżych bucketów, co psuje CORS.
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=AWS_CONFIG.merge(Config(signature_version="s3v4", s3={"addressing_style": "virtual"})),
)


def transact(items, condition_error):
    """Transakcja DynamoDB. Niespełniony warunek -> condition_error, inny konflikt -> 409."""
    try:
        ddb.transact_write_items(TransactItems=items)
    except ddb.exceptions.TransactionCanceledException as e:
        reasons = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
        if "ConditionalCheckFailed" in reasons:
            raise condition_error from e
        raise ApiError(409, "Konflikt zapisu, spróbuj ponownie") from e


def credit_update(partner, delta, require_funds=True):
    """Element transakcji zmieniający saldo kredytów partnera (ujemne delta wymaga środków)."""
    update: dict[str, Any] = {
        "TableName": PARTNERS_TABLE,
        "Key": {"partnerId": partner["partnerId"]},
        "UpdateExpression": "ADD credits :delta",
        "ExpressionAttributeValues": {":delta": delta},
    }
    if delta < 0 and require_funds:
        update["ConditionExpression"] = "credits >= :needed"
        update["ExpressionAttributeValues"][":needed"] = -delta
    return {"Update": update}


def query_by_partner(table, partner):
    """Ostatnie rekordy partnera (indeks byPartner, najnowsze najpierw)."""
    return table.query(
        IndexName="byPartner",
        KeyConditionExpression=Key("partnerId").eq(partner["partnerId"]),
        ScanIndexForward=False,
        Limit=LIST_LIMIT,
    )["Items"]
