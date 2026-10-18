"""Modele wejścia API klienta (Pydantic): parametry ścieżki, query i body na granicy HTTP.

Model sprawdza kształt (typ, wymagane pole); reguły zależne od danych zostają w modułach domeny i dają te same
pola błędów co zawsze: dzień od dziś do 60 dni i filtry (events.parse_filters), opcje ankiety
(onboarding.validate_answers), data urodzenia (account.validate), wgrane zdjęcie (account.own_photo_key).
Trasy wołają `parse_input(Model, dane, "<komunikat>")` z tym samym komunikatem, który daje domena, więc zły typ
i zła wartość kończą się tym samym 400 `{"error", "fields"}`. Nadmiarowe pola pomijamy (domyślne `extra="ignore"`).
"""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

import account

MAX_STATS_IDS = 100

# Parametry ścieżki: id wydarzenia (kal-…, spt-…, demo-…), userId (sub z Cognito, seed-…) i kod znajomego.
# Krótki identyfikator z liter, cyfr, "-" i "_"; wszystko inne -> 404, zanim trafi jako klucz do DynamoDB.
PATH_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _path_id(value: str) -> str:
    if not PATH_ID.fullmatch(value):
        raise ValueError("niepoprawny identyfikator")
    return value


PathId = Annotated[str, AfterValidator(_path_id)]


class EventsQuery(BaseModel):
    """GET /api/events?when=&date=&cat=&district=&free=&indoor=&q=&limit= (wartości: events.parse_filters)."""

    when: str | None = None
    date: str | None = None
    cat: str | None = None
    district: str | None = None
    free: str | None = None
    indoor: str | None = None
    q: str | None = None
    limit: str | None = None


def _id_list(value: object) -> object:
    """Tekst "a, b,,c" -> ["a", "b", "c"] (puste pozycje pomijamy)."""
    if isinstance(value, str):
        return [i.strip() for i in value.split(",") if i.strip()]
    return value


class StatsQuery(BaseModel):
    """GET /api/events/stats?ids=a,b,c - od 1 do MAX_STATS_IDS identyfikatorów."""

    ids: Annotated[list[str], BeforeValidator(_id_list), Field(min_length=1, max_length=MAX_STATS_IDS)]


class ProfileBody(BaseModel):
    """PUT /api/profile {"answers": {pole: opcja | [opcje] | tekst}} (wartości: onboarding.validate_answers)."""

    answers: dict[str, object]


class MeBody(BaseModel):
    """PUT /api/me {"birthDate": "RRRR-MM-DD" | "" | null} (pusta albo brak = usunąć; zakres: account.validate)."""

    birthDate: str | None = None


def _photo_type(value: str) -> str:
    if value not in account.PHOTO_TYPES:
        raise ValueError("nieobsługiwany format zdjęcia")
    return value


class PhotoUploadBody(BaseModel):
    """POST /api/me/photo {"contentType"} - JPG, PNG albo WebP."""

    contentType: Annotated[str, AfterValidator(_photo_type)]


class PhotoBody(BaseModel):
    """PUT /api/me/photo {"key"} - klucz z POST /api/me/photo (czy mój i wgrany: account)."""

    key: str


class InviteBody(BaseModel):
    """POST /api/friends/invite {"code"} - kod wpisany "byle jak" (normalizuje friends.normalize_code)."""

    code: str
