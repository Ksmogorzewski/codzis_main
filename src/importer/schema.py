"""Wspólny schemat rekordu eventu (schemaVersion 1) - docelowa tabela DynamoDB.

Ten sam kształt mają rekordy ze wszystkich źródeł (API UM Warszawy i portal partnera):

    id             str   "<prefiks źródła>-<sha1(klucz źródła)[:12]>"; partner: UUID
    origin         str   um_warszawa (importer, otwarte dane UM) | partner (portal partnera)
    source         str   szczegółowe źródło: um_kalendarz | um_sport | partner
    kind           str   event (konkretne terminy) | recurring (zajęcia co tydzień)
    schemaVersion  int   1
    title          str
    lead           str?  krótki opis, zwykły tekst
    text           str?  pełny opis, HTML (sanityzować przy wyświetlaniu)
    url            str?  strona źródłowa
    category       [{id?, name}]  kategorie ze źródła (podpowiedź dla taggera)
    audience       [str] grupy docelowe ze źródła (np. "Seniorzy")
    district       str?  dzielnica Warszawy
    online         bool
    venue          {name?, address?}
    location       {lat, lon}?
    occurrences    [{start, end?, allDay}]  ISO 8601 z offsetem (kind=event)
    schedule       [{day, start?, end?}]    day: monday..sunday, "HH:MM" (kind=recurring)
    startsAt       str?  UTC, najwcześniejszy start z occurrences (do sortowania/indeksów)
    endsAt         str?  UTC, najpóźniejszy koniec z occurrences
    imageUrl       str?  https (w tabeli: plik w standardzie zdjęć, tagger/images.py)
    sourceImageUrl str?  dopisuje tagger: adres źródłowy zdjęcia
    attributes     {}    dodatki specyficzne dla źródła
    contentHash    str   hash treści - importer wysyła na kolejkę tylko nowe/zmienione rekordy
    importedAt     str   UTC
"""

import hashlib
import json
import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
ORIGIN = "um_warszawa"  # wszystko z importera; portal partnera ustawia origin = "partner"
WARSAW = ZoneInfo("Europe/Warsaw")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Pola pomijane przy liczeniu hasha (zmieniają się przy każdym imporcie)
_VOLATILE = {"contentHash", "importedAt"}


def make_id(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def finalize(record: dict, imported_at: str) -> dict:
    """Uzupełnia pola wyliczane: startsAt/endsAt, contentHash, importedAt."""
    starts = [_parse(o["start"]) for o in record["occurrences"]]
    ends = [_parse(o.get("end") or o["start"]) for o in record["occurrences"]]
    record["schemaVersion"] = SCHEMA_VERSION
    record["origin"] = ORIGIN
    record["startsAt"] = utc(min(starts)) if starts else None
    record["endsAt"] = utc(max(ends)) if ends else None
    record["contentHash"] = content_hash(record)
    record["importedAt"] = imported_at
    return record


def content_hash(record: dict) -> str:
    stable = {k: v for k, v in record.items() if k not in _VOLATILE}
    return hashlib.sha1(json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc() -> str:
    return utc(datetime.now(timezone.utc))


def iso_offset(value: str | None) -> str | None:
    """'2027-01-29T19:00:00+01' (format UM) -> '2027-01-29T19:00:00+01:00'."""
    if not value:
        return None
    return re.sub(r"([+-]\d{2})$", r"\1:00", value)


def warsaw_iso(day: str, hhmm: str | None) -> str:
    """Data + godzina w czasie warszawskim -> ISO z poprawnym offsetem (CET/CEST)."""
    t = time.fromisoformat(hhmm) if hhmm else time(0, 0)
    return datetime.combine(date.fromisoformat(day), t, tzinfo=WARSAW).isoformat()


def hhmm(value: str | None) -> str | None:
    """'9:00' / '20:0' -> '09:00' / '20:00'; None gdy nie da się odczytać."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{1,2})\s*", value or "")
    if not m:
        return None
    h, mnt = int(m.group(1)), int(m.group(2).ljust(2, "0"))
    return f"{h:02d}:{mnt:02d}" if h < 24 and mnt < 60 else None


def https(url: str | None) -> str | None:
    # Zdjęcia UM są linkowane po http://, a na stronie HTTPS przeglądarka je blokuje
    return re.sub(r"^http://", "https://", url) if url else None


def location(geojson_map: dict | None) -> dict | None:
    for feature in (geojson_map or {}).get("features") or []:
        coords = (feature.get("geometry") or {}).get("coordinates")
        if isinstance(coords, list) and len(coords) == 2:
            return {"lon": coords[0], "lat": coords[1]}
    return None


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)
