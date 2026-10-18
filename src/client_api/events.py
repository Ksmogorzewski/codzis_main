"""Wydarzenia (Eksploruj, Popularne, „Twoje”): rekord v1 -> karta, okna czasu, termin, filtry, pamięć scanu.

Czyste funkcje (bez AWS) - DynamoDB obsługuje store.py, HTTP handler.py.

Karta (`card`) ma ten sam kształt co karta rekomendacji z src/recommender_api/present.py, ale bez
`reason`, `reasonSource` i `score`, za to z `saves` (liczba zapisanych) i `saved` (czy ja) - front
używa jednego komponentu karty.

`next_slot` to KOPIA logiki z recommender/retriever/filters.py (rekomender ma własne zależności,
nie importujemy go; tu tylko schemat v1, bez surowego kształtu API UM). Zmiana zasad terminu =
zmiana w obu miejscach.

Kategoria (`category_of`) według tej samej mapy co front: src/frontend/client/lib/categories.ts.
"""

import html
import re
import time as clock
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Wymiary taggera pokazywane na karcie (jak w present.py)
CARD_TAGS = ["theme", "format", "cost", "mode", "setting", "registration", "audience", "activity_level"]

# --- okna czasu (jak src/recommender_api/user_context.py) ---
WHEN = ["today", "tomorrow", "weekend", "week", "date"]
MAX_DAYS_AHEAD = 60

# --- filtry Eksploruj ---
CATEGORIES = ["sport", "kultura", "rekreacja"]
DEFAULT_LIMIT = 60
MAX_LIMIT = 200
MAX_QUERY = 100
FREE = "Bezpłatne"
INDOOR = {"W pomieszczeniu", "W pomieszczeniu i na zewnątrz"}

# Mapa kategorii jak w src/frontend/client/lib/categories.ts
SPORT_THEMES = {"Sport", "Rekreacja i fitness"}
SPORT_FORMATS = {"Trening / zajęcia ruchowe", "Zawody / turniej"}
CULTURE_THEMES = {
    "Teatr i performans",
    "Muzyka",
    "Film i kino",
    "Sztuki wizualne i wystawy",
    "Literatura",
    "Muzea i dziedzictwo",
    "Historia",
    "Architektura i urbanistyka",
}

# --- termin (jak recommender/retriever/filters.py) ---
DEFAULT_DURATION = timedelta(hours=2)  # wydarzenie bez końca trwa tyle
LATE_ARRIVAL = timedelta(minutes=30)  # zajęcia, które zaczęły się tyle temu, jeszcze się liczą
MAX_WINDOW_DAYS = 31  # zajęcia cykliczne szukamy najdalej tyle dni naprzód

CACHE_TTL_S = 300

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ZERO_WIDTH_RE = re.compile(r"[​-‍⁠﻿]")


# --------------------------------------------------------------------------- karta


def plain_text(text: Any) -> str:
    """HTML (pole `text` w schemacie v1) -> zwykły tekst, bez znaków zerowej szerokości."""
    text = html.unescape(_HTML_TAG_RE.sub(" ", str(text or "")))
    return re.sub(r"\s+", " ", _ZERO_WIDTH_RE.sub("", text)).strip()


def card(event: dict, slot: dict | None, saves: int, saved: bool) -> dict:
    """Rekord v1 -> karta (jak present.card bez uzasadnienia) + liczba zapisanych i czy ja."""
    tags = event.get("tags") or {}
    attributes = event.get("attributes") or {}
    return {
        "id": event["id"],
        "title": plain_text(event.get("title")),
        "lead": plain_text(event.get("lead")),
        "url": event.get("url"),
        "ticketUrl": attributes.get("ticketUrl"),
        "imageUrl": event.get("imageUrl"),
        "origin": event.get("origin"),
        "source": event.get("source"),
        "kind": event.get("kind"),
        "partnerName": event.get("partnerName"),
        "district": event.get("district"),
        "venue": event.get("venue"),
        "location": event.get("location"),
        "online": bool(event.get("online")),
        "slot": slot,
        "schedule": event.get("schedule") or [],
        "price": attributes.get("price"),
        "tags": {k: tags[k] for k in CARD_TAGS if tags.get(k)},
        "saves": saves,
        "saved": saved,
    }


def detail(event: dict, slot: dict | None, saves: int, saved: bool) -> dict:
    """Karta + pełny opis (bez HTML), wszystkie terminy i czas odczytu ze źródła."""
    return card(event, slot, saves, saved) | {
        "text": plain_text(event.get("text")),
        "occurrences": event.get("occurrences") or [],
        "importedAt": event.get("importedAt"),
    }


def category_of(tags: dict) -> str:
    """Sport ma pierwszeństwo, potem kultura, reszta to rekreacja (jak categoryOf we froncie)."""
    themes = set(tags.get("theme") or [])
    formats = set(tags.get("format") or [])
    if themes & SPORT_THEMES or formats & SPORT_FORMATS:
        return "sport"
    if themes & CULTURE_THEMES:
        return "kultura"
    return "rekreacja"


# --------------------------------------------------------------------------- okna czasu


def warsaw_today(now: datetime) -> date:
    return now.astimezone(WARSAW).date()


def window(when: str, today: date, day: str | None = None) -> tuple[date, date]:
    """Okno dat (włącznie) dla ?when=, w czasie warszawskim. ValueError przy złej dacie."""
    if when == "date":
        try:
            chosen = date.fromisoformat(day or "")
        except ValueError:
            raise ValueError("Podaj datę w formacie RRRR-MM-DD") from None
        if not today <= chosen <= today + timedelta(days=MAX_DAYS_AHEAD):
            raise ValueError(f"Wybierz dzień od dziś do {MAX_DAYS_AHEAD} dni naprzód")
        return chosen, chosen
    if when == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=1)
    if when == "weekend":
        if today.weekday() == 6:  # niedziela: zostało już tylko dziś
            return today, today
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return saturday, saturday + timedelta(days=1)
    if when == "week":
        return today, today + timedelta(days=6)
    return today, today


# --------------------------------------------------------------------------- termin (port next_slot)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    """ISO -> datetime ze strefą (wartości bez offsetu to czas warszawski)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time())
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=WARSAW)


def event_occurrences(event: dict) -> list[tuple[datetime, datetime | None, bool]]:
    """(start, koniec, cały dzień) każdego terminu, po starcie."""
    out: list[tuple[datetime, datetime | None, bool]] = []
    for occ in event.get("occurrences") or []:
        if isinstance(occ, dict) and (start := _parse_datetime(occ.get("start"))):
            out.append((start, _parse_datetime(occ.get("end")), bool(occ.get("allDay"))))
    return sorted(out, key=lambda o: o[0])


def _is_recurring(event: dict) -> bool:
    return event.get("kind") == "recurring" or (bool(event.get("schedule")) and not event_occurrences(event))


def next_slot(event: dict, date_from: Any = None, date_to: Any = None, now: Any = None) -> dict | None:
    """Pierwszy termin w [date_from, date_to] (daty warszawskie, włącznie), który nie skończył się
    przed `now`; None, gdy brak.

    Wydarzenie z datami -> {"start", "end", "allDay"} (ISO, jak w occurrences)
    Zajęcia co tydzień  -> {"recurring": True, "date", "day", "start", "end"} ("HH:MM"; date/day
                           = None, gdy zajęcia nie mają harmonogramu)
    """
    from_d, to_d, now_dt = _parse_date(date_from), _parse_date(date_to), _parse_datetime(now)
    if _is_recurring(event):
        return _schedule_slot(event, from_d, to_d, now_dt)

    for start, end, all_day in event_occurrences(event):
        local_start = start.astimezone(WARSAW)
        if end:
            finish = end
        elif all_day:
            finish = datetime.combine(local_start.date(), time.max, tzinfo=WARSAW)
        else:
            finish = start + DEFAULT_DURATION
        if now_dt and finish < now_dt:
            continue
        if from_d and finish.astimezone(WARSAW).date() < from_d:
            continue
        if to_d and local_start.date() > to_d:
            break  # po starcie: reszta jest jeszcze później
        return {"start": start.isoformat(), "end": end.isoformat() if end else None, "allDay": all_day}
    return None


def _schedule_slot(event: dict, from_d: date | None, to_d: date | None, now_dt: datetime | None) -> dict | None:
    slots = [s for s in event.get("schedule") or [] if isinstance(s, dict) and s.get("day") in DAYS]
    if not slots:
        # Zajęcia bez harmonogramu: dostępne, ale nie wiadomo kiedy
        return {"recurring": True, "date": None, "day": None, "start": None, "end": None}

    now_local = (now_dt or datetime.now(WARSAW)).astimezone(WARSAW)
    first = max(from_d or now_local.date(), now_local.date()) if now_dt else (from_d or now_local.date())
    last = min(to_d or first + timedelta(days=6), first + timedelta(days=MAX_WINDOW_DAYS))
    slots.sort(key=lambda s: s.get("start") or "")

    day = first
    while day <= last:
        for slot in slots:
            if slot["day"] != DAYS[day.weekday()]:
                continue
            if now_dt and day == now_local.date() and slot.get("start"):
                try:
                    begins: datetime | None = datetime.combine(day, time.fromisoformat(slot["start"]), tzinfo=WARSAW)
                except ValueError:
                    begins = None
                if begins and begins + LATE_ARRIVAL < now_dt:
                    continue
            return {
                "recurring": True,
                "date": day.isoformat(),
                "day": slot["day"],
                "start": slot.get("start"),
                "end": slot.get("end"),
            }
        day += timedelta(days=1)
    return None


def last_slot(event: dict) -> dict | None:
    """Ostatni termin wydarzenia z datami (dla minionych na liście „Twoje”); zajęcia co tydzień -> None."""
    found = event_occurrences(event)
    if _is_recurring(event) or not found:
        return None
    start, end, all_day = found[-1]
    return {"start": start.isoformat(), "end": end.isoformat() if end else None, "allDay": all_day}


def slot_sort_key(slot: dict) -> float:
    """Start terminu jako znacznik czasu; zajęcia bez harmonogramu na końcu."""
    if slot.get("recurring"):
        if not slot.get("date"):
            return float("inf")
        try:
            hour = time.fromisoformat(slot.get("start") or "00:00")
        except ValueError:
            hour = time()
        return datetime.combine(date.fromisoformat(slot["date"]), hour, tzinfo=WARSAW).timestamp()
    start = _parse_datetime(slot.get("start"))
    return start.timestamp() if start else float("inf")


# --------------------------------------------------------------------------- filtry Eksploruj


@dataclass(frozen=True)
class Filters:
    when: str
    date_from: date
    date_to: date
    cat: str | None = None
    district: str | None = None
    free: bool = False
    indoor: bool = False
    query: str = ""  # znormalizowana fraza (fold)
    limit: int = DEFAULT_LIMIT


def parse_filters(params: dict, today: date, districts: list[str]) -> tuple[Filters | None, list[str]]:
    """Parametry ?when=&date=&cat=&district=&free=&indoor=&q=&limit= -> (Filters, lista błędnych pól)."""
    errors: list[str] = []
    when = params.get("when") or "today"
    span: tuple[date, date] | None = None
    if when not in WHEN:
        errors.append("when")
    else:
        try:
            span = window(when, today, params.get("date"))
        except ValueError:
            errors.append("date")

    cat = params.get("cat") or None
    if cat and cat not in CATEGORIES:
        errors.append("cat")
    district = params.get("district") or None
    if district and district not in districts:
        errors.append("district")
    try:
        limit = min(max(int(params.get("limit") or DEFAULT_LIMIT), 1), MAX_LIMIT)
    except ValueError:
        errors.append("limit")
        limit = DEFAULT_LIMIT

    if errors or span is None:
        return None, errors
    return Filters(
        when=when,
        date_from=span[0],
        date_to=span[1],
        cat=cat,
        district=district,
        free=_flag(params.get("free")),
        indoor=_flag(params.get("indoor")),
        query=fold(" ".join((params.get("q") or "").split())[:MAX_QUERY]),
        limit=limit,
    ), []


def matches(event: dict, f: Filters) -> bool:
    """Filtry bez terminu (termin sprawdza next_slot)."""
    tags = event.get("tags") or {}
    if not event.get("id") or not plain_text(event.get("title")):
        return False
    if f.cat and category_of(tags) != f.cat:
        return False
    if f.district and event.get("district") != f.district:
        return False
    if f.free and tags.get("cost") != FREE:
        return False
    if f.indoor and tags.get("setting") not in INDOOR:
        return False
    if f.query:
        haystack = fold(_search_text(event))
        if not all(word in haystack for word in f.query.split()):
            return False
    return True


def explore(events: list[dict], f: Filters, now: datetime) -> list[tuple[dict, dict]]:
    """(wydarzenie, termin) pasujące do filtrów i okna, od najbliższego startu."""
    found = []
    for event in events:
        if not matches(event, f):
            continue
        slot = next_slot(event, f.date_from, f.date_to, now)
        if slot is not None:
            found.append((event, slot))
    found.sort(key=lambda pair: (slot_sort_key(pair[1]), plain_text(pair[0].get("title"))))
    return found


def my_events(
    saves: list[dict], known: dict[str, dict], now: datetime, limit: int
) -> list[tuple[dict, dict | None, dict]]:
    """Zakładka „Twoje”: (wydarzenie, termin, zapis) dla moich zapisów (najnowsze najpierw, maks. `limit`).

    Pomija wydarzenia, których nie ma już w codzis-events (zapisy zostają do analityki). Najpierw
    nadchodzące od najbliższego terminu, potem minione (`zapis["past"] = True`, termin = ostatni)
    od najświeższego."""
    upcoming: list[tuple[dict, dict | None, dict]] = []
    past: list[tuple[dict, dict | None, dict]] = []
    for row in saves:
        event = known.get(row["eventId"])
        if not event:
            continue
        slot = next_slot(event, now=now)
        if slot:
            upcoming.append((event, slot, row | {"past": False}))
        else:
            past.append((event, last_slot(event), row | {"past": True}))
        if len(upcoming) + len(past) == limit:
            break
    upcoming.sort(key=lambda pair: (slot_sort_key(pair[1] or {}), plain_text(pair[0].get("title"))))
    past.sort(key=lambda pair: (-slot_sort_key(pair[1]) if pair[1] else float("inf"), plain_text(pair[0].get("title"))))
    return upcoming + past


def fold(text: str) -> str:
    """Do wyszukiwania: małe litery, bez polskich znaków ("Stodoła" -> "stodola")."""
    text = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    return "".join(c for c in text if not unicodedata.combining(c))


def _search_text(event: dict) -> str:
    venue = event.get("venue") or {}
    tags = event.get("tags") or {}
    parts = [
        plain_text(event.get("title")),
        plain_text(event.get("lead")),
        str(venue.get("name") or ""),
        str(venue.get("address") or ""),
        str(event.get("district") or ""),
        str(event.get("partnerName") or ""),
        *(tags.get("theme") or []),
        *(tags.get("format") or []),
    ]
    return " ".join(parts)


def _flag(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "tak", "yes"}


# --------------------------------------------------------------------------- pamięć scanu


class EventCache:
    """Wszystkie wydarzenia (id -> rekord) z pamięci kontenera Lambdy, odświeżane co `ttl` sekund.

    Świadomy wyjątek od zasady „bez scan w ścieżce żądania” (AGENTS.md): Eksploruj i Popularne
    filtrują po terminie, dzielnicy i tagach, a codzis-events nie ma indeksu po czasie. Przy ~1200
    rekordach jeden scan co 5 min na kontener jest tani; różnice między kontenerami trwają maks.
    5 min. Liczniki zapisów (`saves`) zawsze czytamy z bazy, nie stąd. Docelowo: GSI po czasie.
    """

    def __init__(self, load: Callable[[], dict[str, dict]], ttl: float = CACHE_TTL_S) -> None:
        self.load = load
        self.ttl = ttl
        self.clock: Callable[[], float] = clock.monotonic
        self._loaded_at: float | None = None
        self._events: dict[str, dict] = {}

    def get(self, now: float | None = None) -> dict[str, dict]:
        now = self.clock() if now is None else now
        if self._loaded_at is None or now - self._loaded_at >= self.ttl:
            self._events = self.load()
            self._loaded_at = now
        return self._events
