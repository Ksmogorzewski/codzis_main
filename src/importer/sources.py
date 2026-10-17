"""Źródła danych UM Warszawy: endpoint + mapowanie surowego rekordu na wspólny schemat (schema.py).

Każdy mapper zwraca listę rekordów (bez pól wyliczanych - te dodaje schema.finalize).
Rekord, którego nie da się sensownie zmapować, jest pomijany (zwracana lista bez niego).
"""

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from schema import DAYS, hhmm, https, iso_offset, location, make_id, warsaw_iso

API_BASE = "https://dane.um.warszawa.pl/api/action"


@dataclass(frozen=True)
class Source:
    name: str  # wartość pola "source"
    endpoint: str
    map_records: Callable[[list], list]


# --- wspólne ---

def _names(items) -> list[str]:
    return [i["name"] for i in items or [] if isinstance(i, dict) and i.get("name")]


def _categories(items) -> list[dict]:
    return [{"id": c.get("id"), "name": c["name"]} for c in items or [] if isinstance(c, dict) and c.get("name")]


def _district(record: dict) -> tuple[str | None, bool]:
    """(dzielnica, online) z localization albo z map.features[].properties.district."""
    names = _names(record.get("localization"))
    online = "Online" in names
    names = [n for n in names if n != "Online"]
    if not names:
        for f in (record.get("map") or {}).get("features") or []:
            if (f.get("properties") or {}).get("district"):
                names = [f["properties"]["district"]]
                break
    return (names[0] if names else None), online


def _venue(record: dict) -> dict:
    addresses = record.get("address") or []
    if isinstance(addresses, dict):
        addresses = [addresses]
    first = addresses[0] if addresses else {}
    street = first.get("street")
    if not street:
        for f in (record.get("map") or {}).get("features") or []:
            p = f.get("properties") or {}
            if p.get("shortStreetName"):
                street = " ".join(filter(None, [p["shortStreetName"], p.get("streetNumber")]))
                break
    return {"name": first.get("name"), "address": street}


def _image(record: dict) -> str | None:
    image = record.get("image") or {}
    return https((image.get("highlighted") or {}).get("path") or (image.get("small") or {}).get("path"))


def _strip_html(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _lead(record: dict, max_len: int = 300) -> str | None:
    if record.get("lead"):
        return record["lead"]
    text = _strip_html(record.get("text"))
    return (text[: max_len - 1] + "…") if len(text) > max_len else (text or None)


def _base(record: dict, *, source: str, prefix: str, kind: str) -> dict:
    district, online = _district(record)
    return {
        "id": make_id(prefix, record["url"]),
        "source": source,
        "kind": kind,
        "title": record.get("title"),
        "lead": _lead(record),
        "text": record.get("text"),
        "url": record.get("url"),
        "category": _categories(record.get("category")),
        "audience": [],
        "district": district,
        "online": online,
        "venue": _venue(record),
        "location": location(record.get("map")),
        "occurrences": [],
        "schedule": [],
        "imageUrl": _image(record),
        "attributes": {},
    }


def _ended(occurrences: list[dict]) -> bool:
    if not occurrences:
        return False
    last = max(datetime.fromisoformat(o.get("end") or o["start"]) for o in occurrences)
    return last < datetime.now(timezone.utc)


# --- Kalendarz wydarzeń (bmm_kalendarz_wydarzen) ---

def map_kalendarz(raw: list) -> list:
    out = []
    for r in raw:
        if not r.get("url") or not r.get("title"):
            continue
        record = _base(r, source="um_kalendarz", prefix="kal", kind="event")
        for o in r.get("occurrence") or []:
            if not o.get("from"):
                continue
            record["occurrences"].append(
                {"start": iso_offset(o["from"]), "end": iso_offset(o.get("to")), "allDay": bool(o.get("daily"))}
            )
        if not record["occurrences"] or _ended(record["occurrences"]):
            continue  # bez terminu albo już się odbyło
        out.append(record)
    return out


# --- Zajęcia sportowe (bmm_zajecia_sportowe) ---

def map_sport(raw: list) -> list:
    out = []
    for r in raw:
        if not r.get("url") or not r.get("title"):
            continue
        start = hhmm(r.get("time"))
        days = [d["id"] for d in r.get("day") or [] if isinstance(d, dict) and d.get("id") in DAYS]
        dates = [d for d in r.get("date") or [] if isinstance(d, str)]

        record = _base(r, source="um_sport", prefix="spt", kind="event" if dates else "recurring")
        record["audience"] = _names(r.get("dedicated"))
        if dates:
            record["occurrences"] = [{"start": warsaw_iso(d, start), "end": None, "allDay": start is None} for d in sorted(dates)]
            if _ended(record["occurrences"]):
                continue
        else:
            # Źródło podaje tylko godzinę startu, bez końca
            record["schedule"] = [{"day": d, "start": start, "end": None} for d in DAYS if d in days]
        out.append(record)
    return out


# --- Otwarte boiska (be_otwarte_boiska) ---

BOISKA_DAYS = {
    "Poniedziałek": "monday", "Wtorek": "tuesday", "Środa": "wednesday", "Czwartek": "thursday",
    "Piątek": "friday", "Sobota": "saturday", "Niedziela": "sunday",
}

# Typ obiektu -> tytuł "eventu" (np. boisko piłkarskie = "Piłka nożna")
BOISKA_TITLES = {
    "boiska do piłki nożnej": "Piłka nożna",
    "boiska uniwersalne/wielozadaniowe": "Boisko wielofunkcyjne",
    "boiska do koszykówki": "Koszykówka",
    "bieżnie proste": "Bieżnia prosta",
    "boiska do siatkówki": "Siatkówka",
    "skocznie": "Skocznia (skok w dal)",
    "bieżnie okólne": "Bieżnia okólna",
    "boiska do piłki ręcznej": "Piłka ręczna",
    "siłownia zewnętrzna": "Siłownia zewnętrzna",
    "tenis stołowy": "Tenis stołowy",
    "INNE niż wymienione": "Obiekt sportowy",
    "rzutnie": "Rzutnia",
    "street workout": "Street workout",
    "korty tenisowe": "Tenis",
    "boiska do siatkówki plażowej": "Siatkówka plażowa",
    "skatepark": "Skatepark",
    "boiska do hokeja na trawie": "Hokej na trawie",
    "bulodromy (boiska do gry w pétanque, bule, bocce)": "Pétanque / bule",
    "boiska do badmintona": "Badminton",
    "tor przeszkód": "Tor przeszkód",
}

DAY_SHORT = {"monday": "pon", "tuesday": "wt", "wednesday": "śr", "thursday": "czw", "friday": "pt", "saturday": "sob", "sunday": "nd"}


def _boiska_hours(value: str | None) -> tuple[str, str] | None:
    """'Od 17:00 do 22:00' -> ('17:00', '22:00'); '-' / nieczytelne / 00:00-00:00 -> None (zamknięte)."""
    m = re.fullmatch(r"\s*Od\s+(\S+)\s+do\s+(\S+)\s*", value or "")
    if not m:
        return None
    start, end = hhmm(m.group(1)), hhmm(m.group(2))
    if not start or not end or start == end:
        return None
    return start, end


def _merge_windows(windows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Scala nakładające się okna godzinowe jednego dnia (kilka boisk tego samego typu)."""
    merged: list[list[str]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def map_boiska(raw: list) -> list:
    # Ten sam typ obiektu w tej samej szkole bywa w kilku wierszach (kilka boisk, różne godziny)
    # -> jeden rekord na (szkoła, adres, typ), z sumą okien godzinowych.
    groups: dict[tuple, list] = {}
    for r in raw:
        name, address, kind = r.get("Nazwa placówki oświatowej"), r.get("Adres obiektu"), r.get("Typ obiektu")
        if name and address and kind:
            groups.setdefault((name, address, kind), []).append(r)

    out = []
    for (school, address, obj_type), rows in sorted(groups.items()):
        # Kolejność wierszy z API nie jest stała - sortujemy, żeby contentHash był deterministyczny
        rows = sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))
        windows = {day: [] for day in DAYS}
        for row in rows:
            for pl_day, day in BOISKA_DAYS.items():
                hours = _boiska_hours(row.get(pl_day))
                if hours:
                    windows[day].append(hours)
        schedule = [{"day": day, "start": start, "end": end} for day in DAYS for start, end in _merge_windows(windows[day])]
        if not schedule:
            continue  # obiekt nigdy nieotwarty dla mieszkańców

        first = rows[0]
        # Wartości z wszystkich wierszy grupy (nie z "pierwszego") - wynik nie zależy od kolejności
        surface = ", ".join(sorted({r["Rodzaj nawierzchni"] for r in rows if r.get("Rodzaj nawierzchni")})) or None
        notes = " / ".join(sorted({r["Uwagi"] for r in rows if r.get("Uwagi")})) or None
        sports = sorted({s.strip() for r in rows for s in (r.get("Boisk uniwersalne zawiera") or "").split("-") if s.strip()})
        title_type = BOISKA_TITLES.get(obj_type, obj_type[:1].upper() + obj_type[1:])
        district = first.get("Dzielnica")
        hours_text = ", ".join(f"{DAY_SHORT[s['day']]} {s['start']}–{s['end']}" for s in schedule)
        details = [
            f"Bezpłatny dostęp dla mieszkańców: {obj_type} przy placówce {school}, {address} ({district}).",
            f"Godziny: {hours_text}.",
            f"Nawierzchnia: {surface}." if surface else None,
            f"Do dyspozycji: {', '.join(sports)}." if sports else None,
            f"Uwagi: {notes}" if notes else None,
        ]

        out.append({
            "id": make_id("bsk", f"{school}|{address}|{obj_type}"),
            "source": "um_boiska",
            "kind": "venue",
            "title": f"{title_type} – {school}",
            "lead": details[0],
            "text": "".join(f"<p>{html.escape(d)}</p>" for d in details if d),
            "url": None,
            "category": [{"id": "otwarte_boiska", "name": "Sport"}, {"id": None, "name": obj_type}],
            "audience": [],
            "district": district,
            "online": False,
            "venue": {"name": school, "address": address},
            "location": None,  # źródło nie podaje współrzędnych
            "occurrences": [],
            "schedule": schedule,
            "imageUrl": None,
            "attributes": {
                "facilityType": obj_type,
                "facilities": len(rows),
                "sports": sports,
                "surface": surface,
                "stands": any(r.get("Obiekt wyposażony w trybuny") == "TAK" for r in rows),
                "ballCatchers": any(r.get("Obiekt wyposażony w piłkochwyty") == "TAK" for r in rows),
                "notes": notes,
                "sourceUpdatedAt": max((r.get("Data aktualizacji") or "") for r in rows) or None,
            },
        })
    return out


SOURCES = [
    Source("um_kalendarz", f"{API_BASE}/get_bmm_kalendarz_wydarzen", map_kalendarz),
    Source("um_sport", f"{API_BASE}/get_bmm_zajecia_sportowe", map_sport),
    Source("um_boiska", f"{API_BASE}/get_be_otwarte_boiska", map_boiska),
]
