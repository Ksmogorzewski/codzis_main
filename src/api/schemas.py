"""Modele wejścia API partnera (Pydantic) i ich reguły. Komunikaty i listy `fields` - jak przed refaktorem.

Formularz ogłoszenia (`POST /events`) sprawdza `parse_event`: najpierw reguły pojedynczych pól (`EventBody`),
potem reguły między polami (cena a koszt, daty) - błędy z obu zbierane razem, `fields` posortowane alfabetycznie.
Pole błędne samo w sobie liczy się w regułach między polami jak brak wartości (tak działał dawny formularz).
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, TypedDict

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, ValidationError

from codzis_common.app import ApiError, validation_fields
from config import CATEGORIES, CREDIT_PACKAGES, DISTRICTS

EVENT_FIELDS_ERROR = "Niepoprawne lub brakujące pola"
PAID = "Płatne"
MAX_PRICE = 100_000

# Parametry, które partner deklaruje wprost. Wartości = dokładnie opcje z taksonomii taggera
# (tagger/prompt.py -> DIMENSIONS); tagger nadpisuje nimi zgadywania modelu. Kolejność = kolejność w rekordzie.
FORM_OPTIONS = {
    "cost": ["Bezpłatne", PAID],
    "registration": ["Wstęp wolny", "Wymagane zapisy / rejestracja", "Wymagany bilet"],
    "setting": ["W pomieszczeniu", "Na zewnątrz", "W pomieszczeniu i na zewnątrz"],
    "audience": ["Dzieci (0-12)", "Młodzież (13-17)", "Dorośli (18-64)", "Seniorzy (65+)", "Rodziny / wszystkie grupy"],
    "accessibility": [
        "Dostępne dla osób z niepełnosprawnością ruchową",
        "Tłumaczenie na PJM",
        "Audiodeskrypcja",
        "Przyjazne sensorycznie",
    ],
}

PHOTO_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class Partner(TypedDict):
    """Partner z żądania (token Google albo klucz API) - patrz `routes.current_partner`."""

    partnerId: str
    partnerName: str


class Profile(BaseModel):
    """Odpowiedź `GET /me` (kolejność pól = kolejność w JSON)."""

    partnerId: str
    partnerName: str
    credits: int
    eventCost: int
    formOptions: dict[str, list[str]]


# --- reguły pojedynczych pól: zwracają czystą wartość albo rzucają ValueError (= pole w `fields`) ---


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(max_len: int, required: bool = False) -> Callable[[object], str | None]:
    """Tekst do `max_len` znaków (liczone przed obcięciem spacji); pusty = brak (błąd, gdy pole wymagane)."""

    def check(value: object) -> str | None:
        if _is_blank(value):
            if required:
                raise ValueError("Pole wymagane")
            return None
        if not isinstance(value, str) or len(value) > max_len:
            raise ValueError("Niepoprawny tekst")
        return value.strip()

    return check


def _http_url(value: str | None) -> str | None:
    if value and not re.match(r"https?://", value):
        raise ValueError("Adres musi zaczynać się od http:// albo https://")
    return value


def _one_of(options: list[str]) -> Callable[[object], object]:
    def check(value: object) -> object:
        if value not in options:
            raise ValueError("Wartość spoza listy")
        return value

    return check


def _many_of(options: list[str]) -> Callable[[object], list[str]]:
    """Lista opcji (brak = pusta); wynik w kolejności opcji, bez duplikatów."""

    def check(value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or any(v not in options for v in value):
            raise ValueError("Wartość spoza listy")
        return [option for option in options if option in value]

    return check


def parse_price(value: object) -> Decimal | None:
    """Cena 0..MAX_PRICE zaokrąglona do groszy; pusta = brak ceny."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Niepoprawna cena") from None
    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        raise ValueError("Niepoprawna cena")
    return price.quantize(Decimal("0.01"))


def parse_datetime(value: object) -> datetime | None:
    """ISO 8601 z offsetem strefy, np. 2027-01-29T19:00:00+01:00; cokolwiek innego -> None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _required_datetime(value: object) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError("Niepoprawna data")
    return parsed


def _optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    return _required_datetime(value)


def _known_photo_type(value: object) -> str | None:
    """Nieznany typ zdjęcia nie jest błędem pola: `create_event` zwraca osobny 400 z listą `allowed`."""
    return value if isinstance(value, str) and value in PHOTO_TYPES else None


def _known_package(value: str) -> str:
    if value not in CREDIT_PACKAGES:
        raise ValueError("Nieznany pakiet")
    return value


RequiredText = Annotated[str, BeforeValidator(_text(200, required=True))]
OptionalText = Annotated[str | None, BeforeValidator(_text(200))]
Url = Annotated[str | None, BeforeValidator(_text(500)), AfterValidator(_http_url)]
Price = Annotated[Decimal | None, BeforeValidator(parse_price)]


class EventBody(BaseModel):
    """Formularz ogłoszenia: reguły pojedynczych pól. Nieznane pola są ignorowane.

    Nie używaj samodzielnie - `parse_event` dokłada reguły między polami."""

    title: RequiredText
    lead: Annotated[str, BeforeValidator(_text(500, required=True))]
    text: Annotated[str | None, BeforeValidator(_text(5000))] = None
    venue: RequiredText
    street: OptionalText = None
    streetNumber: Annotated[str | None, BeforeValidator(_text(20))] = None
    url: Url = None
    ticketUrl: Url = None
    cost: Annotated[str, BeforeValidator(_one_of(FORM_OPTIONS["cost"]))]
    registration: Annotated[str, BeforeValidator(_one_of(FORM_OPTIONS["registration"]))]
    setting: Annotated[str, BeforeValidator(_one_of(FORM_OPTIONS["setting"]))]
    audience: Annotated[list[str], BeforeValidator(_many_of(FORM_OPTIONS["audience"]))] = Field(default_factory=list)
    accessibility: Annotated[list[str], BeforeValidator(_many_of(FORM_OPTIONS["accessibility"]))] = Field(
        default_factory=list
    )
    priceMin: Price = None
    priceMax: Price = None
    category: Annotated[str, BeforeValidator(_one_of(CATEGORIES))]
    district: Annotated[str, BeforeValidator(_one_of(DISTRICTS))]
    startsAt: Annotated[datetime, BeforeValidator(_required_datetime)]
    endsAt: Annotated[datetime | None, BeforeValidator(_optional_datetime)] = None
    photoContentType: Annotated[str | None, BeforeValidator(_known_photo_type)] = None

    def declared(self) -> dict[str, Any]:
        """Parametry zadeklarowane wprost (do rekordu: tagger przepisuje je do tagów); puste listy pomijamy."""
        values = {name: getattr(self, name) for name in FORM_OPTIONS}
        return {name: value for name, value in values.items() if value}


def parse_event(body: dict[str, Any]) -> EventBody:
    """Body `POST /events` -> EventBody albo ApiError 400 ze wszystkimi błędnymi polami (posortowane)."""
    errors = _cross_field_errors(body)
    try:
        event = EventBody.model_validate(body)
    except ValidationError as e:
        raise ApiError(400, EVENT_FIELDS_ERROR, fields=sorted({*errors, *validation_fields(e)})) from None
    if errors:
        raise ApiError(400, EVENT_FIELDS_ERROR, fields=sorted(set(errors)))
    return event


def _cross_field_errors(body: dict[str, Any]) -> list[str]:
    """Reguły między polami. Wartość błędna sama w sobie liczy się jak brak (`_valid_or_none`)."""
    errors = []

    cost = body.get("cost") if body.get("cost") in FORM_OPTIONS["cost"] else None
    price_min = _valid_or_none(parse_price, body.get("priceMin"))
    price_max = _valid_or_none(parse_price, body.get("priceMax"))
    if cost and (price_min is not None or price_max is not None):  # bez kosztu błąd zgłasza już pole cost
        if cost != PAID:
            errors.append("priceMin" if price_min is not None else "priceMax")  # cena przy wydarzeniu bezpłatnym
        elif price_min is not None and price_max is not None and price_max < price_min:
            errors.append("priceMax")

    starts, ends = parse_datetime(body.get("startsAt")), parse_datetime(body.get("endsAt"))
    if starts and ends and ends < starts:
        errors.append("endsAt")
    last = ends or starts
    if last and last < datetime.now(UTC):
        errors.append("endsAt" if ends else "startsAt")
    return errors


def _valid_or_none[T](parse: Callable[[object], T | None], value: object) -> T | None:
    try:
        return parse(value)
    except ValueError:
        return None


class PaymentBody(BaseModel):
    """Body `POST /payments`: {"package": id pakietu z CREDIT_PACKAGES}."""

    package: Annotated[str, AfterValidator(_known_package)]


def parse_payment(body: dict[str, Any]) -> PaymentBody:
    """Body `POST /payments` -> PaymentBody albo 400 z listą pakietów (`allowed`, bez `fields` - jak dotąd)."""
    try:
        return PaymentBody.model_validate(body)
    except ValidationError:
        raise ApiError(400, "Nieznany pakiet", allowed=list(CREDIT_PACKAGES)) from None
