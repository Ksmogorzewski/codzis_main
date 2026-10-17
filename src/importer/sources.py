"""Źródła danych UM Warszawy: endpoint + mapowanie surowego rekordu na wspólny schemat (schema.py).

Każdy mapper zwraca listę rekordów (bez pól wyliczanych - te dodaje schema.finalize).
Rekord, którego nie da się sensownie zmapować, jest pomijany (zwracana lista bez niego).
"""

import html
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


# --- Trasy turystyczne (sbt_trasy_turystyczne) ---

MAX_TRACE_POINTS = 200  # pełny ślad ma do ~1300 punktów (~32 KB); na mapę wystarczy uproszczony


def _latlon(lat, lon) -> dict | None:
    try:
        return {"lat": float(lat), "lon": float(lon)}
    except (TypeError, ValueError):
        return None


def _downsample(points: list, max_points: int = MAX_TRACE_POINTS) -> list:
    """Co n-ty punkt + zawsze ostatni (koniec trasy)."""
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


def map_trasy(raw: list) -> list:
    out = []
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        # traces są w kolejności [lat, lon] (odwrotnie niż GeoJSON w kalendarzu)
        trace = [[p[0], p[1]] for p in r.get("traces") or [] if isinstance(p, list) and len(p) == 2]
        points = []
        for p in r.get("tourist_points") or []:
            pos = _latlon((p.get("latlng") or {}).get("lat"), (p.get("latlng") or {}).get("lng"))
            if p.get("name") and pos:
                points.append({"id": p.get("id_point"), "name": p["name"], **pos})
        try:
            length_km = round(float(r.get("length")), 2)
        except (TypeError, ValueError):
            length_km = None

        description = re.sub(r"\s+", " ", r.get("description") or "").strip() or None
        details = [
            description,
            f"Długość trasy: {length_km} km." if length_km else None,
            f"Na trasie: {', '.join(p['name'] for p in points)}." if points else None,
        ]
        start = _latlon(*trace[0]) if trace else ({"lat": points[0]["lat"], "lon": points[0]["lon"]} if points else None)

        out.append({
            "id": make_id("trs", title),  # źródło nie ma id ani url; tytuły są unikalne
            "source": "um_trasy",
            "kind": "route",
            "title": title,
            "lead": description,
            "text": "".join(f"<p>{html.escape(d)}</p>" for d in details if d),
            "url": None,
            "category": [{"id": "trasy_turystyczne", "name": "Turystyka"}],
            "audience": [],
            "district": None,  # trasy przechodzą przez kilka dzielnic
            "online": False,
            "venue": {"name": points[0]["name"] if points else None, "address": None},  # punkt startowy
            "location": start,
            "occurrences": [],
            "schedule": [],  # dostępna o każdej porze
            "imageUrl": None,
            "attributes": {
                "lengthKm": length_km,
                "points": points,
                "trace": _downsample(trace),
                "tracePointsTotal": len(trace),
            },
        })
    return out


SOURCES = [
    Source("um_kalendarz", f"{API_BASE}/get_bmm_kalendarz_wydarzen", map_kalendarz),
    Source("um_sport", f"{API_BASE}/get_bmm_zajecia_sportowe", map_sport),
    Source("um_trasy", f"{API_BASE}/get_sbt_trasy_turystyczne", map_trasy),
]
