"""Onboarding klienta: pytania + mapowanie odpowiedzi na profil pod rekomendacje (RAG).

Jedno źródło prawdy. Frontend dostaje pytania z GET /api/onboarding (bez mapowania) i tylko
je renderuje, a odpowiedzi zamieniane są tutaj na preferencje w słowniku eventów:
  - themes, formats, audience, occasion, activityLevel, cost, mode, setting, registration,
    accessibility -> dokładnie opcje z taksonomii taggera (tagger/prompt.py -> DIMENSIONS)
  - interests -> kategorie źródłowe z kalendarza UM (np. "Kultura", "Czas wolny")
  - days, timeOfDay, weekend -> te same wartości co facets eventów (tagger/facets.py)
  - district -> dzielnica jak w polu district eventów

Dodanie pytania = nowy wpis w build_steps(); frontend nie wymaga zmian.
"""

import hashlib
import json
from typing import Any

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND = ["saturday", "sunday"]
TIMES_OF_DAY = ["rano", "popołudnie", "wieczór"]

# Pola preferencji: listy (sumowane ze wszystkich odpowiedzi) i wartości pojedyncze
LIST_PREFS = [
    "interests", "themes", "formats", "audience", "occasion", "activityLevel",
    "cost", "mode", "setting", "registration", "accessibility", "days", "timeOfDay",
]
SCALAR_PREFS = ["district", "travelRange", "maxPrice", "ageRange"]
BOOL_PREFS = ["weekend"]

# Kolejność i nazwy w tekstowym profilu pod RAG: najpierw pola z przykładu, potem reszta
RAG_FIELDS = [
    ("interests", "interests"), ("district", "district"), ("cost", "cost"), ("mode", "mode"),
    ("audience", "audience"), ("themes", "themes"), ("formats", "formats"), ("occasion", "occasion"),
    ("activityLevel", "activity"), ("setting", "setting"), ("registration", "registration"),
    ("maxPrice", "maxPrice"), ("travelRange", "travel"), ("days", "days"), ("timeOfDay", "timeOfDay"),
    ("weekend", "weekend"), ("accessibility", "accessibility"), ("ageRange", "age"),
]


def _opt(option_id: str, label: str, icon: str | None = None, short: str | None = None, **maps) -> dict:
    """Opcja odpowiedzi. icon = nazwa ikony Material Symbols, short = etykieta na kafelku profilu."""
    unknown = set(maps) - set(LIST_PREFS) - set(SCALAR_PREFS) - set(BOOL_PREFS)
    assert not unknown, f"nieznane pola preferencji: {unknown}"
    return {"id": option_id, "label": label, "icon": icon, "short": short or label, "maps": maps}


def build_steps(districts: list[str]) -> list[dict]:
    """Kroki onboardingu (kafelki profilu). Pole: single (jedna odpowiedź), multi (kilka, opcjonalnie
    maxSelect) albo select (jedna z długiej listy, wyświetlana jako siatka). Krok jest wymagany,
    jeśli ma wymagane pole."""
    return [
        {
            "id": "who", "icon": "group",
            "title": "Z kim planujesz wyjście?", "hint": "Wybierz jedną opcję",
            "fields": [{"id": "who", "type": "single", "required": True, "options": [
                _opt("solo_friends", "Solo, ze znajomymi lub we dwoje", "diversity_3", "Solo / we dwoje",
                     occasion=["Samodzielnie", "Ze znajomymi", "Na randkę"], audience=["Dorośli (18-64)"],
                     interests=["Dla młodzieży i dorosłych"]),
                _opt("kids", "Z dziećmi (atrakcje rodzinne)", "family_restroom", "Z dziećmi",
                     occasion=["Z dziećmi"], audience=["Dzieci (0-12)", "Rodziny / wszystkie grupy"],
                     interests=["Dla dzieci"]),
                _opt("seniors", "Dla seniorów (dla mnie lub bliskich)", "elderly", "Seniorzy",
                     audience=["Seniorzy (65+)"], interests=["Dla seniorów"]),
            ]}],
        },
        {
            "id": "vibe", "icon": "mood",
            "title": "Na jaki klimat masz ochotę?", "hint": "Wybierz maksymalnie 2",
            "fields": [{"id": "vibe", "type": "multi", "required": True, "maxSelect": 2, "options": [
                _opt("chill", "Chill, relaks i rozrywka po godzinach", "weekend", "Chill",
                     themes=["Film i kino", "Kulinaria"], formats=["Pokaz filmowy", "Zabawa / potańcówka"],
                     activityLevel=["Widz / słuchacz"], interests=["Czas wolny"]),
                _opt("art", "Sztuka: koncerty, teatr, wystawy", "theater_comedy", "Sztuka",
                     themes=["Muzyka", "Teatr i performans", "Sztuki wizualne i wystawy"],
                     formats=["Koncert", "Spektakl", "Wystawa"], interests=["Kultura"]),
                _opt("active", "W ruchu! Trening, bieganie, zawody", "directions_run", "W ruchu",
                     themes=["Sport", "Rekreacja i fitness"], formats=["Trening / zajęcia ruchowe", "Zawody / turniej"],
                     activityLevel=["Wysiłek fizyczny"], interests=["Sport"]),
                _opt("health", "Zdrowie, balans i profilaktyka", "spa", "Zdrowie",
                     themes=["Zdrowie i wellness"], interests=["Zdrowie"]),
                _opt("festivals", "Miejskie święta, festyny i rocznice", "celebration", "Święta miejskie",
                     themes=["Święta i festiwale", "Historia"], formats=["Festyn / festiwal / jarmark"],
                     interests=["Święta"]),
            ]}],
        },
        {
            "id": "discover", "icon": "explore",
            "title": "Co chcesz przy okazji odkryć lub rozwinąć?", "hint": "Wybierz maksymalnie 2",
            "fields": [{"id": "discover", "type": "multi", "required": True, "maxSelect": 2, "options": [
                _opt("skills", "Warsztaty, wykłady i nowe skille", "school", "Warsztaty",
                     themes=["Edukacja i warsztaty", "Nauka i technologia"],
                     formats=["Warsztat", "Wykład / prelekcja", "Kurs / szkolenie"],
                     activityLevel=["Udział aktywny"], interests=["Edukacja"]),
                _opt("networking", "Networking, kariera i biznes", "handshake", "Networking",
                     themes=["Biznes i kariera"], formats=["Spotkanie / dyskusja", "Konferencja", "Targi"],
                     occasion=["Poznawanie nowych ludzi"], interests=["Biznes"]),
                _opt("history", "Tajemnice i historia dawnej Warszawy", "castle", "Historia",
                     themes=["Historia", "Muzea i dziedzictwo"], interests=["Historia"]),
                _opt("architecture", "Architektura, urbanistyka i design", "apartment", "Architektura",
                     themes=["Architektura i urbanistyka", "Moda i design"], interests=["Architektura"]),
                _opt("guided", "Zwiedzanie i spacery z przewodnikiem", "tour", "Spacery",
                     themes=["Turystyka i spacery"], formats=["Spacer / wycieczka"], interests=["Turystyka"]),
            ]}],
        },
        {
            "id": "city", "icon": "location_city",
            "title": "Które sprawy miejskie są Ci bliskie?", "hint": "Wybierz dowolne – albo pomiń ten krok",
            "fields": [{"id": "city", "type": "multi", "required": False, "options": [
                _opt("eco", "Zieleń, klimat i ekologia", "park", "Zieleń",
                     themes=["Ekologia i środowisko"], interests=["Ekologia i środowisko"]),
                _opt("community", "Inicjatywy sąsiedzkie i społeczność", "volunteer_activism", "Sąsiedzi",
                     themes=["Społeczność i wolontariat"], interests=["Społeczeństwo"]),
                _opt("safety", "Pierwsza pomoc i bezpieczeństwo", "medical_services", "Bezpieczeństwo",
                     themes=["Bezpieczeństwo"], interests=["Bezpieczeństwo"]),
                _opt("council", "Wpływ na dzielnicę i sesje Rady Miasta", "how_to_vote", "Rada Miasta",
                     themes=["Sprawy miejskie i polityka lokalna"], formats=["Spotkanie / dyskusja"],
                     interests=["Rada Miasta i Rady Dzielnic"]),
            ]}],
        },
        # --- dodatkowe kafelki: dokładniejsze dopasowanie (gdzie, kiedy, za ile, jak) ---
        {
            "id": "where", "icon": "near_me",
            "title": "Gdzie w Warszawie?", "hint": "Podpowiemy wydarzenia blisko Ciebie",
            "fields": [
                {"id": "district", "type": "select", "label": "Twoja dzielnica", "required": True,
                 "options": [_opt(d, d, district=d) for d in districts]},
                {"id": "travel", "type": "single", "label": "Jak daleko chcesz jeździć?", "required": True,
                 "options": [
                    _opt("local", "Tylko moja okolica", "directions_walk", "Okolica", travelRange="local"),
                    _opt("nearby", "Moja i sąsiednie dzielnice", "directions_bus", "Sąsiednie dzielnice",
                         travelRange="nearby"),
                    _opt("city", "Cała Warszawa", "tram", "Cała Warszawa", travelRange="city"),
                ]},
            ],
        },
        {
            "id": "when", "icon": "schedule",
            "title": "Kiedy zwykle masz czas?", "hint": "Opcjonalne – możesz zaznaczyć kilka",
            "fields": [{"id": "when", "type": "multi", "required": False, "options": [
                _opt("weekday_day", "W tygodniu, w ciągu dnia", "light_mode", "W tygodniu w dzień",
                     days=WEEKDAYS, timeOfDay=["rano", "popołudnie"]),
                _opt("weekday_evening", "W tygodniu, po pracy lub szkole", "dark_mode", "Wieczorami",
                     days=WEEKDAYS, timeOfDay=["wieczór"]),
                _opt("weekend", "W weekendy", "calendar_month", "Weekendy",
                     days=WEEKEND, timeOfDay=["rano", "popołudnie", "wieczór"], weekend=True),
            ]}],
        },
        {
            "id": "budget", "icon": "payments",
            "title": "Ile chcesz wydać na wyjście?", "hint": "Opcjonalne – kwota na osobę",
            "fields": [{"id": "budget", "type": "single", "required": False, "options": [
                _opt("free", "Tylko bezpłatne", "savings", "Bezpłatne", cost=["Bezpłatne"], maxPrice=0),
                _opt("up50", "Do 50 zł", "payments", "Do 50 zł", maxPrice=50),
                _opt("up150", "Do 150 zł", "account_balance_wallet", "Do 150 zł", maxPrice=150),
                _opt("any", "Bez znaczenia", "all_inclusive", "Dowolny budżet"),
            ]}],
        },
        {
            "id": "style", "icon": "nature_people",
            "title": "Jak lubisz spędzać czas?", "hint": "Opcjonalne",
            "fields": [
                {"id": "setting", "type": "single", "label": "W środku czy na zewnątrz?", "required": False,
                 "options": [
                    _opt("indoor", "Pod dachem", "roofing", "Pod dachem", setting=["W pomieszczeniu"]),
                    _opt("outdoor", "Na świeżym powietrzu", "park", "Plener", setting=["Na zewnątrz"]),
                    _opt("any", "Bez różnicy", "swap_horiz", "Pod dachem lub plener"),
                ]},
                {"id": "activity", "type": "multi", "label": "Jak aktywnie?", "required": False, "options": [
                    _opt("watch", "Oglądam i słucham", "visibility", "Oglądam", activityLevel=["Widz / słuchacz"]),
                    _opt("participate", "Biorę udział", "front_hand", "Biorę udział", activityLevel=["Udział aktywny"]),
                    _opt("exercise", "Chcę się zmęczyć", "fitness_center", "Wysiłek",
                         activityLevel=["Wysiłek fizyczny"]),
                ]},
            ],
        },
        {
            "id": "format", "icon": "confirmation_number",
            "title": "Jaka formuła wydarzeń?", "hint": "Opcjonalne",
            "fields": [
                {"id": "mode", "type": "single", "label": "Na żywo czy online?", "required": False, "options": [
                    _opt("live", "Tylko na żywo", "location_on", "Na żywo", mode=["Stacjonarne"]),
                    _opt("online_ok", "Online też chętnie", "devices", "Także online",
                         mode=["Stacjonarne", "Hybrydowe", "Online"]),
                ]},
                {"id": "registration", "type": "single", "label": "Zapisy i bilety", "required": False, "options": [
                    _opt("walk_in", "Wolę wpaść bez zapisów", "door_open", "Bez zapisów", registration=["Wstęp wolny"]),
                    _opt("any", "Zapisy i bilety mi nie przeszkadzają", "confirmation_number", "Zapisy OK"),
                ]},
            ],
        },
        {
            "id": "about", "icon": "person",
            "title": "Na koniec kilka słów o Tobie", "hint": "Opcjonalne – pomaga lepiej dobrać propozycje",
            "fields": [
                {"id": "age", "type": "single", "label": "Ile masz lat?", "required": False, "options": [
                    _opt("under18", "Poniżej 18", short="< 18 lat", ageRange="under18", audience=["Młodzież (13-17)"]),
                    _opt("18_29", "18–29", short="18–29 lat", ageRange="18-29", audience=["Dorośli (18-64)"]),
                    _opt("30_49", "30–49", short="30–49 lat", ageRange="30-49", audience=["Dorośli (18-64)"]),
                    _opt("50_64", "50–64", short="50–64 lat", ageRange="50-64", audience=["Dorośli (18-64)"]),
                    _opt("65plus", "65+", short="65+ lat", ageRange="65+", audience=["Seniorzy (65+)"]),
                ]},
                {"id": "accessibility", "type": "multi", "label": "Potrzeby dostępności", "required": False,
                 "options": [
                    _opt("mobility", "Dostęp dla osób z niepełnosprawnością ruchową", "accessible", "Dostęp bez barier",
                         accessibility=["Dostępne dla osób z niepełnosprawnością ruchową"]),
                    _opt("pjm", "Tłumaczenie na PJM", "sign_language", "PJM", accessibility=["Tłumaczenie na PJM"]),
                    _opt("audio", "Audiodeskrypcja", "hearing", "Audiodeskrypcja", accessibility=["Audiodeskrypcja"]),
                    _opt("sensory", "Wydarzenia przyjazne sensorycznie", "self_improvement", "Przyjazne sensorycznie",
                         accessibility=["Przyjazne sensorycznie"]),
                ]},
            ],
        },
    ]


def onboarding_version(steps: list[dict]) -> str:
    """Hash struktury pytań (id pól i opcji + mapowanie, bez etykiet). Zmiana -> profil do odświeżenia."""
    shape = [(f["id"], f["type"], [(o["id"], o["maps"]) for o in f["options"]]) for s in steps for f in s["fields"]]
    return hashlib.sha1(json.dumps(shape, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def public_steps(steps: list[dict]) -> list[dict]:
    """Pytania dla frontendu: bez mapowania na preferencje."""
    return [
        {
            **{k: v for k, v in s.items() if k != "fields"},
            "fields": [
                {**{k: v for k, v in f.items() if k != "options"},
                 "options": [{k: o[k] for k in ("id", "label", "icon", "short")} for o in f["options"]]}
                for f in s["fields"]
            ],
        }
        for s in steps
    ]


def validate_answers(answers, steps: list[dict]) -> tuple[dict, list[str]]:
    """-> (odpowiedzi znormalizowane {pole: [id opcji]}, lista pól z błędem)."""
    fields = {f["id"]: f for s in steps for f in s["fields"]}
    if not isinstance(answers, dict):
        return {}, ["answers"]

    errors = [name for name in answers if name not in fields]
    normalized = {}
    for name, field in fields.items():
        raw = answers.get(name)
        if raw in (None, "", []):
            values = []
        elif isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, list) and all(isinstance(v, str) for v in raw):
            values = list(dict.fromkeys(raw))  # bez duplikatów, w kolejności
        else:
            errors.append(name)
            continue

        allowed = {o["id"] for o in field["options"]}
        if any(v not in allowed for v in values):
            errors.append(name)
        elif field["type"] in ("single", "select") and len(values) > 1:
            errors.append(name)
        elif field.get("maxSelect") and len(values) > field["maxSelect"]:
            errors.append(name)
        elif field["required"] and not values:
            errors.append(name)
        elif values:
            normalized[name] = values
    return normalized, sorted(set(errors))


def compute_preferences(answers: dict, steps: list[dict]) -> dict:
    """Suma mapowań wybranych opcji -> preferencje w słowniku eventów."""
    prefs: dict[str, Any] = (
        {k: [] for k in LIST_PREFS} | {k: None for k in SCALAR_PREFS} | {k: False for k in BOOL_PREFS}
    )
    for step in steps:
        for field in step["fields"]:
            chosen = set(answers.get(field["id"], []))
            for option in field["options"]:
                if option["id"] not in chosen:
                    continue
                for key, value in option["maps"].items():
                    if key in LIST_PREFS:
                        prefs[key] = list(dict.fromkeys(prefs[key] + list(value)))
                    elif key in BOOL_PREFS:
                        prefs[key] = prefs[key] or bool(value)
                    else:
                        prefs[key] = value
    # Kolejność kanoniczna jak w facets eventów
    prefs["days"] = [d for d in WEEKDAYS + WEEKEND if d in prefs["days"]]
    prefs["timeOfDay"] = [t for t in TIMES_OF_DAY if t in prefs["timeOfDay"]]
    return prefs


def rag_profile(prefs: dict) -> str:
    """Tekstowy profil pod RAG, np.
    interests=[Kultura, Czas wolny] | district=Śródmieście | cost=Bezpłatne | mode=Stacjonarne
    | audience=Dorośli (18-64)
    Puste pola są pomijane; lista z jedną wartością wypisywana bez nawiasów."""
    parts = []
    for key, name in RAG_FIELDS:
        value = prefs.get(key)
        if value in (None, [], False) or (key == "maxPrice" and prefs.get("cost") == ["Bezpłatne"]):
            continue
        if isinstance(value, list):
            text = value[0] if len(value) == 1 else "[" + ", ".join(value) + "]"
        elif isinstance(value, bool):
            text = "true"
        else:
            text = str(value)
        parts.append(f"{name}={text}")
    return " | ".join(parts)
