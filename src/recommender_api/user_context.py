"""Profil z onboardingu (tabela users: preferences, ragProfile) -> user_context rekomendera.

Twarde filtry: dzielnica (wg zasięgu dojazdu), koszt, forma (na żywo / online), grupa
odbiorców, budżet i okno czasowe. Reszta preferencji tylko podbija ranking
(recommender/retriever/scoring.py), żeby wąski profil nie kończył się pustą listą.

Wpisana fraza (query) odwraca priorytety: szukamy w całej Warszawie, twarde filtry
z profilu nie obcinają wyników, a preferencje zostają tylko miękkim podbiciem przy remisie
(okno czasowe zostaje - to jawny wybór użytkownika, nie ustawienie z onboardingu).
"""

from datetime import date, datetime, timedelta

# Okna czasowe (parametr ?when=; "date" = wybrany dzień z ?date=RRRR-MM-DD)
WINDOWS = {"today": "dziś", "tomorrow": "jutro", "weekend": "w weekend", "week": "w ciągu 7 dni", "date": "w wybrany dzień"}
MAX_DAYS_AHEAD = 60
# Zasięg dojazdu z onboardingu (travelRange), od najwęższego
AREAS = ["local", "nearby", "city"]

# Sąsiedztwo dzielnic (przybliżone, łącznie z sąsiadami przez Wisłę połączonymi mostem)
_BORDERS = [
    ("Bemowo", "Bielany"), ("Bemowo", "Wola"), ("Bemowo", "Włochy"), ("Bemowo", "Ursus"),
    ("Bielany", "Żoliborz"), ("Bielany", "Wola"), ("Bielany", "Białołęka"),
    ("Żoliborz", "Wola"), ("Żoliborz", "Śródmieście"), ("Żoliborz", "Praga-Północ"), ("Żoliborz", "Białołęka"),
    ("Wola", "Śródmieście"), ("Wola", "Ochota"), ("Wola", "Włochy"),
    ("Śródmieście", "Ochota"), ("Śródmieście", "Mokotów"), ("Śródmieście", "Praga-Północ"), ("Śródmieście", "Praga-Południe"),
    ("Ochota", "Mokotów"), ("Ochota", "Włochy"),
    ("Mokotów", "Włochy"), ("Mokotów", "Ursynów"), ("Mokotów", "Wilanów"), ("Mokotów", "Praga-Południe"),
    ("Włochy", "Ursus"), ("Włochy", "Ursynów"), ("Ursynów", "Wilanów"), ("Wilanów", "Wawer"),
    ("Praga-Północ", "Praga-Południe"), ("Praga-Północ", "Targówek"), ("Praga-Północ", "Białołęka"),
    ("Praga-Południe", "Targówek"), ("Praga-Południe", "Rembertów"), ("Praga-Południe", "Wawer"),
    ("Targówek", "Białołęka"), ("Targówek", "Rembertów"),
    ("Rembertów", "Wawer"), ("Rembertów", "Wesoła"), ("Wawer", "Wesoła"),
]
NEIGHBOURS: dict[str, list[str]] = {}
for _a, _b in _BORDERS:
    NEIGHBOURS.setdefault(_a, []).append(_b)
    NEIGHBOURS.setdefault(_b, []).append(_a)


def window(when: str, today: date, day: str | None = None) -> tuple[date, date]:
    """Okno dat (włącznie) dla ?when=, w czasie warszawskim. ValueError przy złej dacie."""
    if when == "date":
        try:
            chosen = date.fromisoformat(day or "")
        except ValueError:
            raise ValueError("Podaj datę w formacie RRRR-MM-DD")
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


def search_prefs(prefs: dict) -> dict:
    """Profil wyszukiwania frazą: sama dzielnica (podbicie „blisko domu” i lokalizacja dla AI), bez reszty
    preferencji. Wynik frazy jest wspólny dla wszystkich z tej dzielnicy (results_store.search_owner),
    więc nie może zależeć od ani mówić nic o konkretnej osobie."""
    return {"district": prefs["district"]} if prefs.get("district") else {}


def start_area(prefs: dict) -> str:
    return prefs.get("travelRange") if prefs.get("travelRange") in AREAS else "city"


def build_context(prefs: dict, rag_profile: str | None, span: tuple[date, date], query: str, now: datetime, area: str) -> dict:
    home = prefs.get("district")
    near = NEIGHBOURS.get(home, [])
    date_from, date_to = span
    max_price = prefs.get("maxPrice")

    if area == "local" and home:
        districts = [home]
    elif area == "nearby" and home:
        districts = [home, *near]
    else:
        districts = None

    # Wpisana fraza wygrywa z profilem: szukamy w całej Warszawie, bez twardych filtrów
    # z onboardingu; preferencje zostają tylko miękkimi podbiciami przy remisie.
    searching = bool(query)

    return {
        "query": query or None,
        "interests": [] if searching else _unique(prefs.get("themes"), prefs.get("formats"), prefs.get("interests")),
        "profile": rag_profile,
        # twarde filtry (tylko bez frazy)
        "district": None if searching else districts,
        "cost": None if searching else (prefs.get("cost") or None),
        "mode": None if searching else (prefs.get("mode") or None),
        "audience": None if searching else (prefs.get("audience") or None),
        "max_price": None if searching else (float(max_price) if max_price else None),  # 0 = "tylko bezpłatne" załatwia cost
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "now": now.isoformat(timespec="seconds"),
        # miękkie preferencje (przy wyszukiwaniu tematy z profilu nie przebijają wpisanej frazy)
        "themes": [] if query else prefs.get("themes") or [],
        "formats": [] if query else prefs.get("formats") or [],
        "occasion": prefs.get("occasion") or [],
        "activity_level": prefs.get("activityLevel") or [],
        "setting": prefs.get("setting") or [],
        "registration": prefs.get("registration") or [],
        "accessibility": prefs.get("accessibility") or [],
        "time_of_day": prefs.get("timeOfDay") or [],
        "home_district": home,
        "near_districts": near,
    }


def _unique(*lists) -> list[str]:
    return list(dict.fromkeys(v for values in lists for v in values or []))
