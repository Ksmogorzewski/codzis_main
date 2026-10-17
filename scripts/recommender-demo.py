#!/usr/bin/env python
"""Demo / mock-data harness: show what the recommender proposes for each query.

Runs a small hand-written Warsaw event dataset (schema v1 + tagger `tags`) through
the real pipeline and prints the ranking the way a user would see it:

    .venv/bin/python scripts/recommender-demo.py            # cosine ranking
    .venv/bin/python scripts/recommender-demo.py --llm      # + DeepSeek re-rank/reasons

No AWS, no database, no network (beyond the model weights, which are cached after the
first run). Without a DEEPSEEK_API_KEY the LLM steps are skipped automatically, so
`matched` preferences stand in for the "why".

Useful for eyeballing a change: run it before and after touching BOOSTS, min_score,
taste_weight or the embedding text, and see which propositions moved.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recommender import DEFAULT_MIN_SCORE, Recommender  # noqa: E402
from recommender.chunker import event_district  # noqa: E402
from recommender.retriever import make_event_filter  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
TODAY = date.today()
DAYS = ["pon", "wto", "śro", "czw", "pią", "sob", "nie"]


# --------------------------------------------------------------------------- #
# Mock dataset
# --------------------------------------------------------------------------- #
def _sat() -> date:
    """Upcoming Saturday (so the weekend demo query always has something to find)."""
    return TODAY + timedelta(days=(5 - TODAY.weekday()) % 7)


SAT = _sat()
SUN = SAT + timedelta(days=1)


def occ(day: date, hour: int, hours: int = 2) -> list[dict]:
    start = datetime.combine(day, time(hour), tzinfo=WARSAW)
    return [{"start": start.isoformat(), "end": (start + timedelta(hours=hours)).isoformat()}]


def ev(eid, title, lead, category, district, venue, occurrences, **tags):
    return {
        "id": eid,
        "title": title,
        "lead": lead,
        "category": [{"name": category}],
        "district": [{"name": district}],
        "venue": {"name": venue},
        "occurrences": occurrences,
        "tags": tags,
    }


EVENTS = [
    # --- music -------------------------------------------------------------
    ev("jazz-kwiat", "Koncert jazzowy: Kwiat Quintet",
       "Wieczór improwizacji jazzowej, premierowe kompozycje kwinetetu. Wstęp wolny.",
       "Muzyka", "Śródmieście", "Klub Hybrydy", occ(SAT, 20),
       theme=["Jazz", "Muzyka na żywo"], format=["Koncert"], cost="Bezpłatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("chopin", "Recital chopinowski",
       "Fortepian solo w wykonaniu laureata Konkursu Chopinowskiego.",
       "Muzyka", "Śródmieście", "Filharmonia Narodowa", occ(SUN, 18),
       theme=["Muzyka klasyczna"], format=["Koncert"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("rock-noise", "Koncert rockowy: The Warsaw Noise",
       "Głośny koncert zespołu rockowego, support: trzy kapele z Warszawy.",
       "Muzyka", "Wola", "Klub Proxima", occ(SAT, 21),
       theme=["Rock", "Muzyka na żywo"], format=["Koncert"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("online-stream", "Streaming: koncert z Domu Kultury",
       "Transmisja na żywo z sali kameralnej, dostępna z domu.",
       "Muzyka", "Śródmieście", "Dom Kultury Świt", occ(TODAY + timedelta(days=3), 19),
       theme=["Muzyka na żywo"], format=["Koncert"], cost="Bezpłatne",
       mode="Online", setting="W pomieszczeniu"),
    # --- theatre / film ----------------------------------------------------
    ev("hamlet", "Spektakl Hamlet",
       "Klasyka Szekspira w nowej inscenizacji, czas trwania 3 godziny.",
       "Kultura", "Śródmieście", "Teatr Narodowy", occ(TODAY + timedelta(days=1), 19),
       theme=["Teatr"], format=["Spektakl"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("kabaret", "Wieczór kabaretowy",
       "Stand-up i skecze młodych warszawskich komików.",
       "Kultura", "Ochota", "Dom Kultury Rakowiec", occ(TODAY + timedelta(days=4), 20),
       theme=["Teatr"], format=["Spektakl"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór", occasion=["Na randkę"]),
    ev("cinema-open", "Kino plenerowe: klasyka romansu",
       "Seans pod gwiazdami dla zakochanych, przynieś koc i termos.",
       "Film", "Śródmieście", "Bulwary Wiślane", occ(SAT, 21),
       theme=["Film"], format=["Seans"], cost="Bezpłatne",
       setting="Na zewnątrz", time_of_day="wieczór", occasion=["Na randkę"]),
    ev("kino-luna", "Kino studyjne: retrospektywa Kieślowskiego",
       "Pokaz cyfrowo odrestaurowanych filmów, po seansie dyskusja.",
       "Film", "Śródmieście", "Kino Luna", occ(TODAY + timedelta(days=2), 18),
       theme=["Film"], format=["Seans"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    # --- exhibitions -------------------------------------------------------
    ev("msn-modern", "Wystawa: sztuka nowoczesna po 1989",
       "Stała kolekcja malarstwa i instalacji, otwarta codziennie.",
       "Sztuka", "Śródmieście", "Muzeum Sztuki Nowoczesnej",
       [{"start": datetime.combine(TODAY, time(10), tzinfo=WARSAW).isoformat(),
         "end": datetime.combine(TODAY + timedelta(days=60), time(18), tzinfo=WARSAW).isoformat()}],
       theme=["Sztuki wizualne"], format=["Wystawa"], cost="Płatne",
       setting="W pomieszczeniu"),
    ev("foto-60", "Wystawa fotografii: Warszawa lat 60.",
       "Archiwalne zdjęcia stolicy ze zbiorów muzeum.",
       "Sztuka", "Praga-Północ", "Muzeum Pragi", occ(TODAY + timedelta(days=5), 12, 6),
       theme=["Sztuki wizualne", "Historia"], format=["Wystawa"], cost="Płatne",
       setting="W pomieszczeniu"),
    # --- kids / family -----------------------------------------------------
    ev("kids-robot", "Warsztaty robotyki dla dzieci",
       "Budujemy roboty z klocków LEGO, dla dzieci 8-12 lat.",
       "Edukacja", "Śródmieście", "Centrum Nauki Kopernik", occ(TODAY + timedelta(days=1), 11),
       theme=["Nauka", "Technologie"], format=["Warsztaty"], cost="Płatne",
       audience=["Dzieci (7-12)"], setting="W pomieszczeniu"),
    ev("kids-calinka", "Spektakl dla dzieci: Calineczka",
       "Interaktywne przedstawienie dla najmłodszych, 50 minut.",
       "Kultura", "Wilanów", "Dom Kultury Wilanów", occ(SUN, 11),
       theme=["Teatr"], format=["Spektakl"], cost="Płatne",
       audience=["Dzieci (7-12)"], setting="W pomieszczeniu"),
    ev("picnic", "Piknik rodzinny w parku",
       "Gry i zabawy dla całych rodzin, animacje i food trucki.",
       "Czas wolny", "Praga-Południe", "Park Skaryszewski", occ(SUN, 12, 5),
       theme=["Czas wolny"], format=["Piknik"], cost="Bezpłatne",
       audience=["Rodziny / wszystkie grupy"], setting="Na zewnątrz"),
    # --- sport -------------------------------------------------------------
    ev("pool-1", "Zajęcia pływania dla dorosłych - grupa 1",
       "Basen, poziom podstawowy, instruktor, 8 osób w grupie.",
       "Sport", "Śródmieście", "Pływalnia Polna", occ(TODAY + timedelta(days=2), 17, 1),
       theme=["Sport"], format=["Zajęcia"], cost="Płatne",
       audience=["Dorośli (18-64)"], setting="W pomieszczeniu"),
    ev("pool-2", "Zajęcia pływania dla dorosłych - grupa 2",
       "Basen, poziom podstawowy, instruktor, 8 osób w grupie.",
       "Sport", "Śródmieście", "Pływalnia Polna", occ(TODAY + timedelta(days=4), 17, 1),
       theme=["Sport"], format=["Zajęcia"], cost="Płatne",
       audience=["Dorośli (18-64)"], setting="W pomieszczeniu"),
    ev("jogging", "Poranny jogging po Wiśle",
       "Wspólny trening biegowy dla każdego poziomu, 6 km wzdłuż bulwarów.",
       "Sport", "Śródmieście", "Bulwary Wiślane", occ(SUN, 8, 2),
       theme=["Bieganie", "Sport"], format=["Trening"], cost="Bezpłatne",
       setting="Na zewnątrz", time_of_day="rano"),
    ev("yoga-park", "Joga w parku",
       "Zajęcia na trawie, mata we własnym zakresie, poziom otwarty.",
       "Sport", "Wola", "Park Moczydło", occ(SAT, 9, 2),
       theme=["Joga", "Sport"], format=["Zajęcia"], cost="Bezpłatne",
       setting="Na zewnątrz", time_of_day="rano"),
    ev("seniors-gym", "Gimnastyka dla seniorów",
       "Łagodne ćwiczenia z fizjoterapeutą, krzesła zapewnione.",
       "Sport", "Mokotów", "Dom Kultury Kłobucka", occ(TODAY + timedelta(days=3), 10, 1),
       theme=["Sport", "Zdrowie"], format=["Zajęcia"], cost="Bezpłatne",
       audience=["Seniorzy (65+)"], setting="W pomieszczeniu", time_of_day="rano"),
    ev("salsa", "Potanówka: salsa dla początkujących",
       "Pierwsza lekcja gratis, bez partnera, luźna atmosfera.",
       "Taniec", "Praga-Południe", "Terminal Kultury Gocław", occ(TODAY + timedelta(days=2), 19),
       theme=["Taniec"], format=["Zajęcia"], cost="Bezpłatne",
       audience=["Dorośli (18-64)"], setting="W pomieszczeniu",
       time_of_day="wieczór", occasion=["Na randkę"]),
    # --- food --------------------------------------------------------------
    ev("kolacja", "Kolacja degustacyjna kuchni włoskiej",
       "Pięciodaniowe menu z winem, kameralna sala, rezerwacja obowiązkowa.",
       "Kulinaria", "Śródmieście", "Hala Koszyki", occ(SAT, 19, 3),
       theme=["Kulinaria"], format=["Kolacja"], cost="Płatne",
       setting="W pomieszczeniu", time_of_day="wieczór", occasion=["Na randkę"]),
    ev("cook-workshop", "Warsztaty gotowania dla dorosłych",
       "Kuchnia włoska: makarony od podstaw, składniki w cenie.",
       "Kulinaria", "Mokotów", "Pracownia Smaku", occ(TODAY + timedelta(days=6), 18, 3),
       theme=["Kulinaria"], format=["Warsztaty"], cost="Płatne",
       audience=["Dorośli (18-64)"], setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("targ-sniadaniowy", "Targ śniadaniowy",
       "Lokalni producenci, food trucki, strefa relaksu.",
       "Kulinaria", "Żoliborz", "Park im. Żeromskiego", occ(SAT, 9, 5),
       theme=["Kulinaria", "Czas wolny"], format=["Targ"], cost="Bezpłatne",
       audience=["Rodziny / wszystkie grupy"], setting="Na zewnątrz", time_of_day="rano"),
    # --- learning ----------------------------------------------------------
    ev("wyklad-ai", "Wykład o sztucznej inteligencji",
       "Otwarty wykład o uczeniu maszynowym i jego ograniczeniach.",
       "Edukacja", "Śródmieście", "Politechnika Warszawska", occ(TODAY + timedelta(days=2), 18),
       theme=["Nauka", "Technologie"], format=["Wykład"], cost="Bezpłatne",
       audience=["Dorośli (18-64)"], setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("wyklad-astro", "Wykład: nocne niebo nad Warszawą",
       "Jak czytać mapę nieba, obserwacja przez teleskop po wykładzie.",
       "Edukacja", "Bemowo", "Obserwatorium", occ(TODAY + timedelta(days=7), 19),
       theme=["Nauka"], format=["Wykład"], cost="Bezpłatne",
       setting="W pomieszczeniu", time_of_day="wieczór"),
    ev("planszowki", "Planszówki w bibliotece",
       "Otwarte granie, kilkaset gier, pomoc wolontariuszy.",
       "Czas wolny", "Ochota", "Biblioteka Narodowa", occ(SUN, 14, 4),
       theme=["Czas wolny"], format=["Spotkanie"], cost="Bezpłatne",
       setting="W pomieszczeniu", audience=["Rodziny / wszystkie grupy"]),
]

# --------------------------------------------------------------------------- #
# Queries: (label, user_context)
# --------------------------------------------------------------------------- #
QUERIES = [
    ("darmowy koncert muzyki na żywo",
     {"query": "darmowy koncert muzyki na żywo", "cost": "Bezpłatne"}),
    ("coś na randkę wieczorem",
     {"query": "coś na randkę wieczorem", "occasion": ["Na randkę"],
      "time_of_day": ["wieczór"]}),
    ("coś dla dziecka",
     {"query": "coś dla dziecka", "audience": "Dzieci (7-12)"}),
    ("sport na świeżym powietrzu",
     {"query": "sport na świeżym powietrzu", "setting": ["Na zewnątrz"], "themes": ["Sport"]}),
    ("wystawa sztuki (tylko Śródmieście)",
     {"query": "wystawa sztuki", "district": "Śródmieście"}),
    ("czego mogę się nauczyć za darmo",
     {"query": "czego mogę się nauczyć za darmo", "themes": ["Nauka"], "cost": "Bezpłatne"}),
    ("koncert w weekend",
     {"query": "koncert", "date_from": SAT.isoformat(), "date_to": SUN.isoformat()}),
    ("zajęcia ruchowe dla seniora",
     {"query": "zajęcia ruchowe", "audience": "Seniorzy (65+)"}),
    ("[personalisacja] użytkownik polubił koncert jazzowy",
     {"query": "", "liked_event_ids": ["jazz-kwiat"]}),
    ("coś ciekawego (celowo mgliste)",
     {"query": "coś ciekawego"}),
]


# --------------------------------------------------------------------------- #
# Pretty printing
# --------------------------------------------------------------------------- #
def fmt_slot(slot: dict | None) -> str:
    if not slot:
        return "—"
    if slot.get("start"):
        try:
            dt = datetime.fromisoformat(slot["start"]).astimezone(WARSAW)
            return f"{DAYS[dt.weekday()]} {dt:%d.%m %H:%M}"
        except ValueError:
            return slot["start"]
    return "terminy tygodniowe"


def fmt_matched(matched: dict) -> str:
    if not matched:
        return "brak dopasowań preferencji"
    return ", ".join(f"{k}={v}" for k, v in matched.items())


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Show recommender output on mock Warsaw data.")
    parser.add_argument("--llm", action="store_true",
                        help="use DeepSeek for re-ranking + Polish reasons (needs a key)")
    parser.add_argument("--query", help="run this single query instead of the demo set")
    parser.add_argument("--top", type=int, default=5, help="how many propositions to show")
    parser.add_argument("--district", help="with --query: restrict to one district")
    parser.add_argument("--floor", type=float, default=DEFAULT_MIN_SCORE,
                        help="cosine floor (0 disables it)")
    args = parser.parse_args()

    explain = args.llm
    print(f"Model: mpnet (768d)   próg trafności: {args.floor}   "
          f"re-rank LLM: {'tak' if explain else 'nie'}")
    print(f"Eventów w indeksie: {len(EVENTS)}   (daty względem {TODAY}, weekend: {SAT}–{SUN})")
    print("Uwaga: kolejność na liście to wynik po dywersyfikacji (kara za powtórzone")
    print("       miejsce/temat), dlatego `score` nie zawsze maleje monotonicznie.")

    rec = Recommender(EVENTS, api_key=None)
    if explain and rec.client is None:
        print("  (--llm podano, ale nie ma klucza DEEPSEEK_API_KEY -> ranking cosine)")
        explain = False
    floor = args.floor or None

    def run(user: dict):
        predicate = make_event_filter(user)
        passed = sum(1 for e in EVENTS if predicate(e))
        results = rec.recommend(user, top_k=args.top, explain=explain and rec.client is not None,
                                min_score=floor)
        print(f"\n{'=' * 78}\nQUERY: {user.get('query') or '(brak zapytania)'}")
        filters = {k: v for k, v in user.items()
                   if k not in ("query", "liked_event_ids", "profile") and v}
        if user.get("liked_event_ids"):
            filters["liked_event_ids"] = user["liked_event_ids"]
        print(f"FILTRY: {filters or '—'}")
        if rec.last_expansion:
            print(f"ROZSZERZENIE LLM: {rec.last_expansion}")
        print("-" * 78)
        if not results:
            print("  (brak propozycji powyżej progu trafności)")
        for i, c in enumerate(results, 1):
            e = c.event
            print(f"{i:2d}. {e['title']}")
            print(f"    cos={c.metadata['cosine']:.3f}  boost={c.metadata['boost']:+.3f}  "
                  f"score={c.score:.3f}  |  {event_district(e) or '?'}  |  "
                  f"{fmt_slot(c.metadata.get('slot'))}")
            print(f"    matched: {fmt_matched(c.metadata.get('matched') or {})}")
            if c.metadata.get("reason"):
                print(f"    dlaczego: {c.metadata['reason']}")
        print("-" * 78)
        print(f"  pokazano {len(results)}  |  odrzucone filtrami: {len(EVENTS) - passed}  |  "
              f"odrzucone progiem {args.floor}: {rec.last_dropped}  |  "
              f"kandydaci po filtrach: {passed}")

    if args.query:
        user = {"query": args.query}
        if args.district:
            user["district"] = args.district
        run(user)
        return

    for _, user in QUERIES:
        run(user)

    # Show what the relevance floor is doing on the vaguest query.
    vague = {"query": "coś ciekawego"}
    for floor_v, label in ((floor, f"próg {args.floor} (domyślny)"), (None, "bez progu")):
        out = rec.recommend(vague, top_k=10, explain=False, min_score=floor_v)
        print(f"\n{'=' * 78}\nWPŁYW PROGU na „coś ciekawego” — {label}")
        print("-" * 78)
        for i, c in enumerate(out, 1):
            print(f"{i:2d}. cos={c.metadata['cosine']:.3f}  {c.event['title']}")
        print("-" * 78)
        print(f"  zwrócono {len(out)} z 10 proszonych (odrzucone progiem: {rec.last_dropped})")


if __name__ == "__main__":
    main()
