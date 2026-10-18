"""Dane konta w profilu: nazwisko, data urodzenia i zdjęcie profilowe.

Imienia tu nie ma: zostaje z rejestracji albo z Google (atrybut Cognito `name`, w users `displayName`)
i się nie zmienia, bo widzą je inni zapisani na wydarzenie.

Rekord users.account (mapa): lastName, birthDate (RRRR-MM-DD), photoUrl, photoKey (nasze zdjęcie w S3).
Pierwsze GET /api/me zakłada mapę z tokenu - przy Google nazwisko (family_name) i zdjęcie (picture);
potem zmienia ją tylko użytkownik, kolejne logowania jej nie ruszają. Nazwisko i datę urodzenia widzi
tylko właściciel konta.

Zdjęcia: bucket zdjęć ogłoszeń (PHOTOS_BUCKET), klucz photos/avatars/<userId>/<losowe>.<ext>, upload
presigned POST prosto z przeglądarki, odczyt przez CloudFront panelu pod /photos/* (PHOTOS_BASE_URL).
"""

import logging
import os
import re
import secrets
from datetime import date
from typing import Any, TypeGuard

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

PHOTOS_BUCKET = os.environ.get("PHOTOS_BUCKET", "")
PHOTOS_BASE_URL = os.environ.get("PHOTOS_BASE_URL", "").rstrip("/")
MAX_LAST_NAME = 60
MIN_BIRTH_DATE = date(1900, 1, 1)
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # przeglądarka i tak zmniejsza zdjęcie przed wysyłką
UPLOAD_EXPIRES_S = 300
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Regionalny endpoint - globalny potrafi zwracać 307 dla świeżych bucketów, co psuje CORS (jak src/api/store.py).
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://s3.{os.environ.get('AWS_REGION', 'eu-central-1')}.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)
log = logging.getLogger()


def prefill(claims: dict) -> dict:
    """Mapa account przy pierwszym logowaniu: z Google nazwisko i zdjęcie, jeśli są w tokenie."""
    account = {}
    last = _clean(claims.get("family_name"))
    if last and len(last) <= MAX_LAST_NAME:
        account["lastName"] = last
    picture = claims.get("picture")
    if isinstance(picture, str) and picture.startswith("https://"):
        account["photoUrl"] = picture
    return account


def validate(body: dict, today: date) -> tuple[dict, list[str]]:
    """PUT /api/me {lastName, birthDate} -> (wartości, błędne pola). Puste albo brak pola = usunąć."""
    values: dict[str, Any] = {}
    errors = []

    last = body.get("lastName")
    cleaned = _clean(last) if isinstance(last, str) else ""
    if (last is not None and not isinstance(last, str)) or len(cleaned) > MAX_LAST_NAME:
        errors.append("lastName")
    else:
        values["lastName"] = cleaned or None

    birth = body.get("birthDate")
    if birth is None or birth == "":
        values["birthDate"] = None
    elif isinstance(birth, str) and _ISO_DATE.fullmatch(birth) and _birth_date_ok(birth, today):
        values["birthDate"] = birth
    else:
        errors.append("birthDate")
    return values, errors


def merge(current: dict, values: dict) -> dict:
    """Nowa mapa account: None usuwa pole (pustych wartości nie zapisujemy)."""
    return {k: v for k, v in {**current, **values}.items() if v is not None}


def with_photo(current: dict, key: str | None) -> dict:
    """Mapa account z naszym zdjęciem (klucz w S3) albo bez żadnego zdjęcia (None)."""
    account = {k: v for k, v in current.items() if k not in ("photoUrl", "photoKey")}
    if key:
        account.update(photoKey=key, photoUrl=f"{PHOTOS_BASE_URL}/{key}")
    return account


def view(account: dict | None) -> dict:
    account = account or {}
    return {k: account.get(k) for k in ("lastName", "birthDate", "photoUrl")}


# --- S3 ---


def upload_form(user_id: str, content_type: str) -> dict:
    """Presigned POST na nowe zdjęcie; profil zmienia dopiero PUT /api/me/photo z tym kluczem."""
    key = f"photos/avatars/{user_id}/{secrets.token_hex(8)}.{PHOTO_TYPES[content_type]}"
    upload = s3.generate_presigned_post(
        Bucket=PHOTOS_BUCKET,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, MAX_PHOTO_BYTES]],
        ExpiresIn=UPLOAD_EXPIRES_S,
    )
    return {"key": key, "upload": upload}


def own_photo_key(key: object, user_id: str) -> TypeGuard[str]:
    """Klucz w kształcie z upload_form i w katalogu tego użytkownika."""
    pattern = rf"photos/avatars/{re.escape(user_id)}/[0-9a-f]{{16}}\.(jpg|png|webp)"
    return isinstance(key, str) and re.fullmatch(pattern, key) is not None


def uploaded(key: str) -> bool:
    try:
        s3.head_object(Bucket=PHOTOS_BUCKET, Key=key)
        return True
    except ClientError:
        return False


def delete_file(key: str | None) -> None:
    """Usuwa poprzednie zdjęcie; błąd tylko w logu (zostaje niepotrzebny plik, profil działa)."""
    if not key:
        return
    try:
        s3.delete_object(Bucket=PHOTOS_BUCKET, Key=key)
    except (BotoCoreError, ClientError):
        log.warning("Nie udało się usunąć starego zdjęcia profilowego")


def _birth_date_ok(value: str, today: date) -> bool:
    try:
        return MIN_BIRTH_DATE <= date.fromisoformat(value) <= today
    except ValueError:
        return False


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())
