#!/usr/bin/env python
"""End-to-end rundown on a schema-v1 fake DB.

There is no data file in the repo, so this builds one that matches
src/importer/schema.py exactly (schemaVersion 1, DynamoDB record shape, produced via
the importer's own `finalize()` for startsAt/endsAt/contentHash/importedAt) and adds
the `tags`/`facets` that the tagger pipeline would produce.

Then it runs a series of user prompts through the real recommender and prints the
top-5 for each, with cosine / soft boost / final score / district / slot / matched
preferences / reason.

    .venv/bin/python scripts/fake-db-demo.py                 # rundown
    .venv/bin/python scripts/fake-db-demo.py --dump /tmp/e.json
    .venv/bin/python scripts/fake-db-demo.py --llm           # + DeepSeek reasons
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recommender import DEFAULT_MIN_SCORE, Recommender  # noqa: E402
from recommender.chunker import event_district  # noqa: E402
from recommender.retriever import make_event_filter  # noqa: E402
from src.importer.schema import finalize, make_id, now_utc  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
TODAY = date.today()
DAYS_PL = ["pon", "wto", "śro", "czw", "pią", "sob", "nie"]
SAT = TODAY + timedelta(days=(5 - TODAY.weekday()) % 7)
SUN = SAT + timedelta(days=1)
DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# --------------------------------------------------------------------------- #
# Fake DB (schema v1 + tagger output)
# --------------------------------------------------------------------------- #
def _day(when) -> date:
    if when == "sat":
        return SAT
    if when == "sun":
        return SUN
    return TODAY + timedelta(days=int(when))


def E(eid, title, lead, category, district, venue, when, hour, hours=2, *,
      themes=(), fmt="Koncert", cost="Płatne", mode="Stacjonarne",
      setting="W pomieszczeniu", audience=None, occasion=None, price=None,
      online=False, recurring=None, tod=None):
    """One schema-v1 event record + the tags/facets the tagger would add."""
    day = _day(when)
    start = datetime.combine(day, time(hour), tzinfo=WARSAW)
    end = start + timedelta(hours=hours)
    record = {
        "id": make_id("um_kalendarz", f"{eid}-{when}-{hour}"),
        "source": "um_kalendarz",
        "kind": "recurring" if recurring else "event",
        "title": title,
        "lead": lead,
        "text": f"<p>{lead}</p>",
        "url": f"https://example.invalid/events/{eid}",
        "category": [{"id": "1", "name": category}],
        "audience": list(audience or []),
        "district": district,
        "online": online,
        "venue": {"name": venue, "address": f"{district}, Warszawa"},
        "location": {"lat": 52.23, "lon": 21.01},
        "occurrences": [{"start": start.isoformat(), "end": end.isoformat(), "allDay": False}],
        "imageUrl": f"https://example.invalid/img/{eid}.jpg",
        "attributes": {"price": price} if price is not None else {},
        "tags": {
            "theme": list(themes),
            "format": [fmt],
            "cost": cost,
            "mode": mode,
            "setting": setting,
            **({"audience": list(audience)} if audience else {}),
            **({"occasion": list(occasion)} if occasion else {}),
        },
        "facets": {
            "timeOfDay": [tod] if tod else [],
            "multiDay": False,
            "weekday": [DAY_KEYS[day.weekday()]],
        },
    }
    if recurring:
        record["schedule"] = [{"day": recurring, "start": f"{hour:02d}:00",
                               "end": f"{hour + hours:02d}:00"}]
    return finalize(record, now_utc())


def build_db() -> list[dict]:
    P = "Płatne"
    F = "Bezpłatne"
    return [
        # ---------------- muzyka ----------------
        E("jazz-kwiat", "Koncert jazzowy: Kwiat Quintet",
          "Wieczór improwizacji jazzowej, premierowe kompozycje kwinetetu.",
          "Muzyka", "Śródmieście", "Klub Hybrydy", "sat", 20,
          themes=("Jazz", "Muzyka na żywo"), fmt="Koncert", cost=F, tod="wieczór"),
        E("chopin", "Recital chopinowski",
          "Fortepian solo w wykonaniu laureata Konkursu Chopinowskiego.",
          "Muzyka", "Śródmieście", "Filharmonia Narodowa", "sun", 18,
          themes=("Muzyka klasyczna",), fmt="Koncert", cost=P, tod="wieczór"),
        E("rock-noise", "Koncert rockowy: The Warsaw Noise",
          "Głośny koncert zespołu rockowego, support: trzy kapele z Warszawy.",
          "Muzyka", "Wola", "Klub Proxima", "sat", 21,
          themes=("Rock", "Muzyka na żywo"), cost=P, tod="wieczór"),
        E("hiphop", "Koncert hip-hop: Scena Młodych",
          "Trzy składy z Warszawy, bitwy freestyle na koniec.",
          "Muzyka", "Praga-Północ", "Hydrozagadka", 3, 20,
          themes=("Hip-hop",), cost=P, audience=("Młodzież (13-17)", "Dorośli (18-64)"),
          tod="wieczór"),
        E("organy", "Koncert organowy w katedrze",
          "Muzyka barokowa na organach, wstęp bezpłatny.",
          "Muzyka", "Śródmieście", "Archikatedra św. Jana", "sun", 16,
          themes=("Muzyka klasyczna",), cost=F, tod="popołudnie"),
        E("online-stream", "Streaming: koncert z Domu Kultury",
          "Transmisja na żywo z sali kameralnej, dostępna z domu.",
          "Muzyka", "Śródmieście", "Dom Kultury Świt", 2, 19,
          themes=("Muzyka na żywo",), cost=F, mode="Online", online=True, tod="wieczór"),
        E("folk", "Wieczór pieśni ukraińskich",
          "Chór kameralny i zespół instrumentalny, repertuar ludowy.",
          "Muzyka", "Mokotów", "Dom Kultury Kłobucka", 4, 18,
          themes=("Muzyka folkowa",), cost=F, tod="wieczór"),
        # ---------------- teatr / film ----------------
        E("hamlet", "Spektakl Hamlet",
          "Klasyka Szekspira w nowej inscenizacji, czas trwania 3 godziny.",
          "Kultura", "Śródmieście", "Teatr Narodowy", 1, 19, 3,
          themes=("Teatr",), fmt="Spektakl", cost=P, tod="wieczór"),
        E("kabaret", "Wieczór kabaretowy",
          "Stand-up i skecze młodych warszawskich komików.",
          "Kultura", "Ochota", "Dom Kultury Rakowiec", 4, 20,
          themes=("Teatr", "Humor"), fmt="Spektakl", cost=P, tod="wieczór",
          occasion=("Na randkę",)),
        E("kids-calinka", "Spektakl dla dzieci: Calineczka",
          "Interaktywne przedstawienie dla najmłodszych, 50 minut.",
          "Kultura", "Wilanów", "Dom Kultury Wilanów", "sun", 11,
          themes=("Teatr",), fmt="Spektakl", cost=P,
          audience=("Dzieci (7-12)",), tod="rano"),
        E("improv", "Improvizacja teatralna: wieczór otwarty",
          "Krótkie formy improwizowane na podstawie sugestii publiczności.",
          "Kultura", "Praga-Południe", "Terminal Kultury Gocław", 5, 19,
          themes=("Teatr", "Humor"), fmt="Spektakl", cost=F, tod="wieczór",
          occasion=("Na randkę",)),
        E("cinema-open", "Kino plenerowe: klasyka romansu",
          "Seans pod gwiazdami dla zakochanych, przynieś koc i termos.",
          "Film", "Śródmieście", "Bulwary Wiślane", "sat", 21,
          themes=("Film",), fmt="Seans", cost=F, setting="Na zewnątrz",
          tod="wieczór", occasion=("Na randkę",)),
        E("kino-luna", "Kino studyjne: retrospektywa Kieślowskiego",
          "Pokaz cyfrowo odrestaurowanych filmów, po seansie dyskusja.",
          "Film", "Śródmieście", "Kino Luna", 2, 18,
          themes=("Film",), fmt="Seans", cost=P, tod="wieczór"),
        E("kino-dzieci", "Poranek filmowy dla dzieci",
          "Zestaw krótkich animacji, po seansie warsztaty plastyczne.",
          "Film", "Bielany", "Kino Wisła", "sun", 10,
          themes=("Film",), fmt="Seans", cost=F, audience=("Dzieci (7-12)",), tod="rano"),
        E("docfest", "Festiwal filmów dokumentalnych",
          "Cztery dni projekcji i spotkań z reżyserami.",
          "Film", "Wola", "Kino Muranów", "sat", 15, 5,
          themes=("Film",), fmt="Seans", cost=P, tod="popołudnie"),
        # ---------------- sztuka ----------------
        E("msn-modern", "Wystawa: sztuka nowoczesna po 1989",
          "Stała kolekcja malarstwa i instalacji, otwarta codziennie.",
          "Sztuka", "Śródmieście", "Muzeum Sztuki Nowoczesnej", "sat", 10, 8,
          themes=("Sztuki wizualne",), fmt="Wystawa", cost=P),
        E("foto-60", "Wystawa fotografii: Warszawa lat 60.",
          "Archiwalne zdjęcia stolicy ze zbiorów muzeum.",
          "Sztuka", "Praga-Północ", "Muzeum Pragi", 5, 12, 6,
          themes=("Sztuki wizualne", "Historia"), fmt="Wystawa", cost=P, tod="popołudnie"),
        E("plakat", "Wystawa polskiej szkoły plakatu",
          "Ikony polskiego plakatu filmowego i teatralnego.",
          "Sztuka", "Mokotów", "Galeria Kordegarda", 3, 11, 7,
          themes=("Sztuki wizualne", "Design"), fmt="Wystawa", cost=F, tod="rano"),
        E("muz-noc", "Noc Muzeów: trasa Śródmieście",
          "Dziesięć muzeów otwartych do północy, jeden bilet.",
          "Sztuka", "Śródmieście", "Muzeum Narodowe", 6, 18, 6,
          themes=("Sztuki wizualne", "Historia"), fmt="Wystawa", cost=P, tod="wieczór"),
        # ---------------- dzieci / rodzina ----------------
        E("kids-robot", "Warsztaty robotyki dla dzieci",
          "Budujemy roboty z klocków LEGO, dla dzieci 8-12 lat.",
          "Edukacja", "Śródmieście", "Centrum Nauki Kopernik", 1, 11,
          themes=("Nauka", "Technologie"), fmt="Warsztaty", cost=P,
          audience=("Dzieci (7-12)",), tod="rano"),
        E("kids-code", "Nauka programowania dla dzieci: Scratch",
          "Pierwsze kroki w programowaniu, komputery na miejscu.",
          "Edukacja", "Mokotów", "Biblioteka Mokotów", 2, 17,
          themes=("Nauka", "Technologie"), fmt="Warsztaty", cost=F,
          audience=("Dzieci (7-12)",), tod="popołudnie"),
        E("picnic", "Piknik rodzinny w parku",
          "Gry i zabawy dla całych rodzin, animacje i food trucki.",
          "Czas wolny", "Praga-Południe", "Park Skaryszewski", "sun", 12, 5,
          themes=("Czas wolny",), fmt="Piknik", cost=F, setting="Na zewnątrz",
          audience=("Rodziny / wszystkie grupy",), tod="popołudnie"),
        E("zoo", "Nocne zwiedzanie zoo",
          "Zwiedzanie z przewodnikiem po zmroku, obowiązują zapisy.",
          "Czas wolny", "Praga-Północ", "ZOO Warszawa", "sat", 19, 3,
          themes=("Przyroda",), fmt="Wycieczka", cost=P, setting="Na zewnątrz",
          audience=("Rodziny / wszystkie grupy",), tod="wieczór"),
        E("science-show", "Pokazy naukowe dla rodzin",
          "Eksperymenty na żywo, dwie tury po 45 minut.",
          "Edukacja", "Śródmieście", "Centrum Nauki Kopernik", "sun", 13,
          themes=("Nauka",), fmt="Pokaz", cost=P,
          audience=("Rodziny / wszystkie grupy",), tod="popołudnie"),
        # ---------------- sport ----------------
        E("pool-1", "Zajęcia pływania dla dorosłych - grupa 1",
          "Basen, poziom podstawowy, instruktor, 8 osób w grupie.",
          "Sport", "Śródmieście", "Pływalnia Polna", 2, 17, 1,
          themes=("Sport",), fmt="Zajęcia", cost=P, audience=("Dorośli (18-64)",),
          tod="popołudnie", recurring="wednesday"),
        E("pool-2", "Zajęcia pływania dla dorosłych - grupa 2",
          "Basen, poziom podstawowy, instruktor, 8 osób w grupie.",
          "Sport", "Śródmieście", "Pływalnia Polna", 4, 17, 1,
          themes=("Sport",), fmt="Zajęcia", cost=P, audience=("Dorośli (18-64)",),
          tod="popołudnie", recurring="friday"),
        E("jogging", "Poranny jogging po Wiśle",
          "Wspólny trening biegowy dla każdego poziomu, 6 km wzdłuż bulwarów.",
          "Sport", "Śródmieście", "Bulwary Wiślane", "sun", 8, 2,
          themes=("Bieganie", "Sport"), fmt="Trening", cost=F,
          setting="Na zewnątrz", tod="rano"),
        E("yoga-park", "Joga w parku",
          "Zajęcia na trawie, mata we własnym zakresie, poziom otwarty.",
          "Sport", "Wola", "Park Moczydło", "sat", 9, 2,
          themes=("Joga", "Sport"), fmt="Zajęcia", cost=F, setting="Na zewnątrz",
          tod="rano"),
        E("seniors-gym", "Gimnastyka dla seniorów",
          "Łagodne ćwiczenia z fizjoterapeutą, krzesła zapewnione.",
          "Sport", "Mokotów", "Dom Kultury Kłobucka", 3, 10, 1,
          themes=("Sport", "Zdrowie"), fmt="Zajęcia", cost=F,
          audience=("Seniorzy (65+)",), tod="rano", recurring="thursday"),
        E("climbing", "Wspinaczka: otwarte ściany dla początkujących",
          "Instruktor, sprzęt w cenie, zapisy na miejscu.",
          "Sport", "Praga-Południe", "Ściana wspinaczkowa Gocław", 5, 18,
          themes=("Sport",), fmt="Zajęcia", cost=P,
          audience=("Dorośli (18-64)",), tod="wieczór"),
        E("cycling", "Wycieczka rowerowa: Mosty Warszawy",
          "25 km w spokojnym tempie, własny rower.",
          "Sport", "Żoliborz", "Plac Wilsona", "sat", 10, 4,
          themes=("Sport", "Czas wolny"), fmt="Wycieczka", cost=F,
          setting="Na zewnątrz", tod="rano"),
        E("salsa", "Potanówka: salsa dla początkujących",
          "Pierwsza lekcja gratis, bez partnera, luźna atmosfera.",
          "Taniec", "Praga-Południe", "Terminal Kultury Gocław", 2, 19,
          themes=("Taniec",), fmt="Zajęcia", cost=F, audience=("Dorośli (18-64)",),
          tod="wieczór", occasion=("Na randkę",)),
        # ---------------- jedzenie ----------------
        E("kolacja", "Kolacja degustacyjna kuchni włoskiej",
          "Pięciodaniowe menu z winem, kameralna sala, rezerwacja obowiązkowa.",
          "Kulinaria", "Śródmieście", "Hala Koszyki", "sat", 19, 3,
          themes=("Kulinaria",), fmt="Kolacja", cost=P, price=240, tod="wieczór",
          occasion=("Na randkę",)),
        E("cook-workshop", "Warsztaty gotowania dla dorosłych",
          "Kuchnia włoska: makarony od podstaw, składniki w cenie.",
          "Kulinaria", "Mokotów", "Pracownia Smaku", 6, 18, 3,
          themes=("Kulinaria",), fmt="Warsztaty", cost=P, price=180,
          audience=("Dorośli (18-64)",), tod="wieczór"),
        E("targ-sniadaniowy", "Targ śniadaniowy",
          "Lokalni producenci, food trucki, strefa relaksu.",
          "Kulinaria", "Żoliborz", "Park im. Żeromskiego", "sat", 9, 5,
          themes=("Kulinaria", "Czas wolny"), fmt="Targ", cost=F,
          setting="Na zewnątrz", audience=("Rodziny / wszystkie grupy",), tod="rano"),
        E("wino", "Degustacja win gruzińskich",
          "Sześć win, prowadzący sommelier, przekąski w cenie.",
          "Kulinaria", "Śródmieście", "Wine Bar Rytm", 4, 19,
          themes=("Kulinaria",), fmt="Degustacja", cost=P, price=150,
          audience=("Dorośli (18-64)",), tod="wieczór", occasion=("Na randkę",)),
        E("streetfood", "Festiwal street foodu",
          "Trzydzieści food trucków z całej Polski, strefa muzyki.",
          "Kulinaria", "Wola", "Park Sowińskiego", "sun", 12, 7,
          themes=("Kulinaria",), fmt="Festiwal", cost=F, setting="Na zewnątrz",
          audience=("Rodziny / wszystkie grupy",), tod="popołudnie"),
        # ---------------- nauka / rozwój ----------------
        E("wyklad-ai", "Wykład o sztucznej inteligencji",
          "Otwarty wykład o uczeniu maszynowym i jego ograniczeniach.",
          "Edukacja", "Śródmieście", "Politechnika Warszawska", 2, 18,
          themes=("Nauka", "Technologie"), fmt="Wykład", cost=F,
          audience=("Dorośli (18-64)",), tod="wieczór"),
        E("wyklad-astro", "Wykład: nocne niebo nad Warszawą",
          "Jak czytać mapę nieba, obserwacja przez teleskop po wykładzie.",
          "Edukacja", "Bemowo", "Obserwatorium", 6, 19,
          themes=("Nauka",), fmt="Wykład", cost=F, tod="wieczór"),
        E("polski-dla-obcych", "Język polski dla obcokrajowców",
          "Poziom A1, małe grupy, lektor native speaker.",
          "Edukacja", "Śródmieście", "Szkoła językowa Lingwa", 1, 18,
          themes=("Nauka",), fmt="Kurs", cost=P, audience=("Dorośli (18-64)",),
          tod="wieczór", recurring="tuesday"),
        E("spacer-hist", "Spacer historyczny: Warszawa międzywojenna",
          "Dwie godziny z przewodnikiem po Śródmieściu.",
          "Edukacja", "Śródmieście", "Plac Piłsudskiego", "sat", 11, 2,
          themes=("Historia",), fmt="Spacer", cost=F, setting="Na zewnątrz",
          audience=("Dorośli (18-64)", "Seniorzy (65+)"), tod="rano"),
        E("webinar", "Webinar: jak znaleźć pracę w IT",
          "Rekruterzy opowiadają o procesie, pytania na żywo.",
          "Edukacja", "Śródmieście", "On-line", 3, 17,
          themes=("Nauka", "Praca"), fmt="Wykład", cost=F, mode="Online",
          online=True, audience=("Dorośli (18-64)",), tod="popołudnie"),
        # ---------------- czas wolny / inne ----------------
        E("planszowki", "Planszówki w bibliotece",
          "Otwarte granie, kilkaset gier, pomoc wolontariuszy.",
          "Czas wolny", "Ochota", "Biblioteka Narodowa", "sun", 14, 4,
          themes=("Czas wolny",), fmt="Spotkanie", cost=F,
          setting="W pomieszczeniu", audience=("Rodziny / wszystkie grupy",),
          tod="popołudnie"),
        E("ksiazkowy", "Klub czytelniczy: reportaż polski",
          "Rozmowa o jednej książce miesięcznie, nowi mile widziani.",
          "Czas wolny", "Mokotów", "Księgarnia Bagatela", 4, 18,
          themes=("Literatura",), fmt="Spotkanie", cost=F,
          audience=("Dorośli (18-64)",), tod="wieczór"),
        E("standup", "Stand-up: open mic",
          "Dwanaście krótkich występów, wstęp wolny.",
          "Kultura", "Praga-Północ", "Klub Hydrozagadka", 5, 20,
          themes=("Humor",), fmt="Spektakl", cost=F,
          audience=("Dorośli (18-64)",), tod="wieczór", occasion=("Na randkę",)),
        E("wolontariat", "Dzień wolontariatu: sadzenie drzew",
          "Wspólne sadzenie w parku, sprzęt zapewniony.",
          "Czas wolny", "Bielany", "Las Młociny", "sat", 10, 3,
          themes=("Czas wolny", "Przyroda"), fmt="Wolontariat", cost=F,
          setting="Na zewnątrz", audience=("Dorośli (18-64)",), tod="rano"),
        E("pchli-targ", "Pchli targ na Kole",
          "Antyki, starocie i rękodzieło, ponad stu wystawców.",
          "Czas wolny", "Wola", "Targ na Kole", "sun", 8, 5,
          themes=("Czas wolny", "Design"), fmt="Targ", cost=F,
          setting="Na zewnątrz", audience=("Rodziny / wszystkie grupy",), tod="rano"),
        E("escape", "Escape room: zagadka Warszawy",
          "Pokój dla 2-5 osób, poziom średni, rezerwacja online.",
          "Czas wolny", "Śródmieście", "Escape Warszawa", 3, 16,
          themes=("Czas wolny",), fmt="Gra", cost=P, price=120,
          audience=("Dorośli (18-64)",), tod="popołudnie", occasion=("Na randkę",)),
    ]


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
PROMPTS = [
    ("chcę iść na koncert jazzowy w sobotę", {}),
    ("coś na randkę wieczorem, nie za drogo", {"max_price": 160, "occasion": ["Na randkę"]}),
    ("coś dla dziecka w weekend", {"audience": "Dzieci (7-12)"}),
    ("darmowe warsztaty dla dorosłych", {"cost": "Bezpłatne", "themes": ["Nauka"]}),
    ("wystawa sztuki nowoczesnej", {"district": "Śródmieście"}),
    ("sport na świeżym powietrzu rano", {"setting": ["Na zewnątrz"], "time_of_day": ["rano"]}),
    ("coś spokojnego dla seniora", {"audience": "Seniorzy (65+)"}),
    ("nauka programowania dla dzieci", {"audience": "Dzieci (7-12)", "themes": ["Technologie"]}),
    ("kolacja we dwoje", {"occasion": ["Na randkę"], "time_of_day": ["wieczór"]}),
    ("coś ciekawego", {}),
]


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def fmt_slot(slot: dict | None) -> str:
    if not slot:
        return "—"
    if slot.get("recurring"):
        # next_slot() returns {recurring, date, day, start: "HH:MM"} for weekly classes
        day, hh = slot.get("date"), slot.get("start") or ""
        if day:
            d = date.fromisoformat(day)
            return f"{DAYS_PL[d.weekday()]} {d:%d.%m} {hh}".strip()
        return hh or "co tydzień"
    if slot.get("start"):
        try:
            dt = datetime.fromisoformat(slot["start"]).astimezone(WARSAW)
            return f"{DAYS_PL[dt.weekday()]} {dt:%d.%m %H:%M}"
        except ValueError:
            return slot["start"][:16]
    return "—"


def fmt_matched(matched: dict) -> str:
    if not matched:
        return ""
    return ", ".join(f"{k}={','.join(v) if isinstance(v, list) else v}" for k, v in matched.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="write the generated schema-v1 records to this JSON file")
    ap.add_argument("--llm", action="store_true", help="use DeepSeek for re-rank + reasons")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    db = build_db()
    if args.dump:
        Path(args.dump).write_text(json.dumps(db, ensure_ascii=False, indent=1))
        print(f"zapisano {len(db)} rekordów -> {args.dump}")

    print(f"DB: {len(db)} rekordów schema-v1 (origin={db[0]['origin']}, "
          f"schemaVersion={db[0]['schemaVersion']})")
    print(f"    kind=event: {sum(1 for e in db if e['kind'] == 'event')}, "
          f"kind=recurring: {sum(1 for e in db if e['kind'] == 'recurring')}, "
          f"online: {sum(1 for e in db if e['online'])}")
    print(f"    dzielnice: {len({e['district'] for e in db})}, "
          f"darmowe: {sum(1 for e in db if e['tags'].get('cost') == 'Bezpłatne')}")
    print(f"    przykładowy rekord: {json.dumps({k: db[0][k] for k in ('id','startsAt','contentHash')}, ensure_ascii=False)}")

    rec = Recommender(db, api_key=None)
    explain = args.llm and rec.client is not None
    if args.llm and rec.client is None:
        print("    (--llm: brak klucza DEEPSEEK_API_KEY -> tylko cosine)")

    for prompt, extra in PROMPTS:
        user = {"query": prompt, **extra}
        predicate = make_event_filter(user)
        passed = sum(1 for e in db if predicate(e))
        results = rec.recommend(user, top_k=args.top, explain=explain)
        print(f"\n{'─' * 118}")
        print(f"PROMPT: „{prompt}”" + (f"   +filtry: {extra}" if extra else ""))
        print(f"{'─' * 118}")
        print(f"{'#':>2}  {'cos':>5}  {'boost':>6}  {'score':>5}  "
              f"{'tytuł':<40}  {'dzielnica':<15}  {'termin':<15} matched")
        if not results:
            print("   (brak propozycji powyżej progu)")
        for i, c in enumerate(results, 1):
            e = c.event
            print(f"{i:>2}  {c.metadata['cosine']:>5.3f}  {c.metadata['boost']:>+6.3f}  "
                  f"{c.score:>5.3f}  {e['title'][:40]:<40}  "
                  f"{(event_district(e) or '?'):<15}  {fmt_slot(c.metadata.get('slot')):<15} "
                  f"{fmt_matched(c.metadata.get('matched') or {})}")
            if c.metadata.get("reason"):
                print(f"    ↳ {c.metadata['reason']}")
        print(f"   → pokazano {len(results)} | po filtrach {passed}/{len(db)} | "
              f"odrzucone progiem {DEFAULT_MIN_SCORE}: {rec.last_dropped}")


if __name__ == "__main__":
    main()
