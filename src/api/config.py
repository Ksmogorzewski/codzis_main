"""Konfiguracja Lambdy API partnera ze zmiennych środowiskowych (ustawia Terraform: infra/lambda.tf)."""

import json
import os
from decimal import Decimal

SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
EVENTS_QUEUE_URL = os.environ["EVENTS_QUEUE_URL"]
PARTNERS_TABLE = os.environ["PARTNERS_TABLE"]
PAYMENTS_TABLE = os.environ["PAYMENTS_TABLE"]
PHOTOS_BUCKET = os.environ["PHOTOS_BUCKET"]
MAX_PHOTO_BYTES = int(os.environ.get("MAX_PHOTO_BYTES", 5 * 1024 * 1024))
EVENT_COST = int(os.environ.get("EVENT_COST_CREDITS", 1))
STARTER_CREDITS = int(os.environ.get("STARTER_CREDITS", 0))
CREDIT_PACKAGES = json.loads(os.environ["CREDIT_PACKAGES"], parse_float=Decimal)  # id -> {name, credits, price}
CURRENCY = os.environ.get("CURRENCY", "PLN")
PARTNERS = json.loads(os.environ.get("PARTNERS", "{}"))  # apiKeyId -> nazwa partnera
CATEGORIES = json.loads(os.environ["CATEGORIES"])
DISTRICTS = json.loads(os.environ["DISTRICTS"])
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]  # zdjęcia serwuje CloudFront pod /photos/*
REGION = os.environ["AWS_REGION"]
UPLOAD_EXPIRES_S = 300
LIST_LIMIT = 50
