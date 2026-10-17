# Rundown: recommender on a fake schema-v1 DB

A snapshot of what the recommender actually proposes, per user prompt. Useful for
eyeballing a change: run before/after and compare the tables.

**Dataset** — no event data exists in this repo, so `scripts/fake-db-demo.py` generates
48 records that match `src/importer/schema.py` (schemaVersion 1, DynamoDB shape),
produced through the importer's own `finalize()`, so `startsAt` / `endsAt` /
`contentHash` are genuine. Tagger output (`tags`, `facets`) added on top.

```
48 rekordów schema-v1 | kind=event: 44, kind=recurring: 4, online: 2
10 dzielnic | 26 darmowych | model: mpnet 768d | próg trafności (min_score): 0.30
```

**Reproduce**

```bash
.venv/bin/python scripts/fake-db-demo.py            # rundown
.venv/bin/python scripts/fake-db-demo.py --llm      # + DeepSeek re-rank/reasons
.venv/bin/python scripts/fake-db-demo.py --dump /tmp/events.json
```

Columns: `cos` = raw cosine on the best chunk, `boost` = soft-preference
boosts/penalties, `score` = cos + boost (what ranks the list). List order is
post-diversification, so `score` is not always strictly descending.

---

## 1. „chcę iść na koncert jazzowy w sobotę”

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.543 | +0.000 | 0.543 | Koncert jazzowy: Kwiat Quintet | Śródmieście | sob 24.10 20:00 | |
| 2 | 0.438 | +0.000 | 0.438 | Koncert organowy w katedrze | Śródmieście | **nie** 25.10 16:00 | |
| 3 | 0.397 | +0.000 | 0.397 | Kino plenerowe: klasyka romansu | Śródmieście | sob 24.10 21:00 | |
| 4 | 0.396 | +0.000 | 0.396 | Nocne zwiedzanie zoo | Praga-Północ | sob 24.10 19:00 | |
| 5 | 0.384 | +0.000 | 0.384 | Noc Muzeów: trasa Śródmieście | Śródmieście | sob 24.10 18:00 | |

`pokazano 5 | po filtrach 48/48 | odrzucone progiem 0.30: 34`

- ✅ Jazz concert #1 with a clear 0.10 gap.
- ❌ **„w sobotę" is ignored** — #2 is a Sunday concert. Free-text dates are never parsed.

## 2. „coś na randkę wieczorem, nie za drogo”

`+ filtry: max_price=160, occasion=['Na randkę']`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.570 | +0.030 | 0.600 | Kino plenerowe: klasyka romansu | Śródmieście | sob 24.10 21:00 | occasion=Na randkę |
| 2 | 0.522 | +0.000 | 0.522 | Nocne zwiedzanie zoo | Praga-Północ | sob 24.10 19:00 | |
| 3 | 0.480 | +0.030 | 0.510 | Potanówka: salsa dla początkujących | Praga-Południe | wto 20.10 19:00 | occasion=Na randkę |
| 4 | 0.476 | +0.000 | 0.476 | Planszówki w bibliotece | Ochota | nie 25.10 14:00 | |
| 5 | 0.454 | +0.000 | 0.454 | Piknik rodzinny w parku | Praga-Południe | nie 25.10 12:00 | |

`pokazano 5 | po filtrach 46/48 | odrzucone progiem 0.30: 29`

- ✅ Outdoor cinema for two.
- ⚠️ *Zoo* (family event, no `occasion` match) edges out *salsa* (explicit
  `occasion=Na randkę`) by 0.012.

## 3. „coś dla dziecka w weekend”

`+ filtry: audience='Dzieci (7-12)'`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.686 | +0.000 | 0.686 | Piknik rodzinny w parku | Praga-Południe | nie 25.10 12:00 | *(tag: Rodziny)* |
| 2 | 0.592 | +0.000 | 0.592 | Poranek filmowy dla dzieci | Bielany | nie 25.10 10:00 | *(tag: Dzieci)* |
| 3 | 0.499 | +0.000 | 0.499 | Targ śniadaniowy | Żoliborz | sob 24.10 09:00 | *(tag: Rodziny)* |
| 4 | 0.480 | +0.000 | 0.480 | Nocne zwiedzanie zoo | Praga-Północ | sob 24.10 19:00 | |
| 5 | 0.481 | +0.000 | 0.481 | Planszówki w bibliotece | Ochota | nie 25.10 14:00 | |

`pokazano 5 | po filtrach 32/48 | odrzucone progiem 0.30: 16`

- ❌ **`Warsztaty robotyki dla dzieci` and `Nauka programowania dla dzieci` are missing**
  — the only events with an explicit kids tag. Matching `audience` earns **zero boost**;
  only a *missing* tag is penalised.

## 4. „darmowe warsztaty dla dorosłych”

`+ filtry: cost='Bezpłatne', themes=['Nauka']`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.467 | +0.080 | 0.547 | Nauka programowania **dla dzieci**: Scratch | Mokotów | wto 20.10 17:00 | themes=Nauka |
| 2 | 0.540 | +0.000 | 0.540 | Planszówki w bibliotece | Ochota | nie 25.10 14:00 | |
| 3 | 0.517 | +0.000 | 0.517 | Gimnastyka **dla seniorów** | Mokotów | czw 22.10 10:00 | |
| 4 | 0.490 | +0.000 | 0.490 | Potanówka: salsa dla początkujących | Praga-Południe | wto 20.10 19:00 | |
| 5 | 0.427 | +0.050 | 0.477 | Webinar: jak znaleźć pracę w IT | Śródmieście | śro 21.10 17:00 | themes=Nauka |

`pokazano 5 | po filtrach 26/48 | odrzucone progiem 0.30: 10`

- ❌ **Worst result of the run.** „dla dorosłych" is ignored, so a children's course is
  #1 and a seniors' gym class is #3.

## 5. „wystawa sztuki nowoczesnej”

`+ filtry: district='Śródmieście'`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.812 | +0.000 | 0.812 | Wystawa: sztuka nowoczesna po 1989 | Śródmieście | sob 24.10 10:00 | |
| 2 | 0.623 | +0.000 | 0.623 | Noc Muzeów: trasa Śródmieście | Śródmieście | sob 24.10 18:00 | |
| 3 | 0.507 | +0.000 | 0.507 | Kino studyjne: retrospektywa Kieślowskiego | Śródmieście | wto 20.10 18:00 | |
| 4 | 0.438 | +0.000 | 0.438 | Kino plenerowe: klasyka romansu | Śródmieście | sob 24.10 21:00 | |
| 5 | 0.405 | +0.000 | 0.405 | Pokazy naukowe dla rodzin | Śródmieście | nie 25.10 13:00 | |

`pokazano 5 | po filtrach 21/48 | odrzucone progiem 0.30: 8`

- ✅ **Best result in the set** — 0.812 with clear separation.

## 6. „sport na świeżym powietrzu rano”

`+ filtry: setting=['Na zewnątrz'], time_of_day=['rano']`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.762 | +0.050 | 0.812 | Joga w parku | Wola | sob 24.10 09:00 | setting=Na zewnątrz, time_of_day=rano |
| 2 | 0.695 | +0.050 | 0.745 | Poranny jogging po Wiśle | Śródmieście | nie 25.10 08:00 | setting=Na zewnątrz, time_of_day=rano |
| 3 | 0.591 | +0.030 | 0.621 | Gimnastyka dla seniorów | Mokotów | czw 22.10 10:00 | time_of_day=rano — **indoor** |
| 4 | 0.547 | +0.050 | 0.597 | Dzień wolontariatu: sadzenie drzew | Bielany | sob 24.10 10:00 | setting=Na zewnątrz, time_of_day=rano |
| 5 | 0.543 | −0.040 | 0.503 | Wspinaczka: otwarte ściany dla początkujących | Praga-Południe | pią 23.10 18:00 | |

`pokazano 5 | po filtrach 48/48 | odrzucone progiem 0.30: 30`

- ✅ Top-2 perfect.
- ❌ **An indoor gym ranks #3 for "na świeżym powietrzu"** — `setting` contradictions are
  not penalised (only time / audience / online are).
- ✅ #5 correctly took −0.040 for 18:00 vs. „rano".

## 7. „coś spokojnego dla seniora”

`+ filtry: audience='Seniorzy (65+)'`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.498 | +0.000 | 0.498 | Gimnastyka dla seniorów | Mokotów | czw 22.10 10:00 | *(tag: Seniorzy)* |
| 2 | 0.448 | +0.000 | 0.448 | Planszówki w bibliotece | Ochota | nie 25.10 14:00 | |
| 3 | 0.435 | +0.000 | 0.435 | Nocne zwiedzanie zoo | Praga-Północ | sob 24.10 19:00 | |
| 4 | 0.419 | +0.000 | 0.419 | Targ śniadaniowy | Żoliborz | sob 24.10 09:00 | |
| 5 | 0.408 | +0.000 | 0.408 | Piknik rodzinny w parku | Praga-Południe | nie 25.10 12:00 | |

`pokazano 5 | po filtrach 44/48 | odrzucone progiem 0.30: 30`

- ⚠️ Only #1 carries the senior tag; the rest are untagged and ranked on generic
  similarity. „spokojnego" is not a taggable dimension at all.

## 8. „nauka programowania dla dzieci”

`+ filtry: audience='Dzieci (7-12)', themes=['Technologie']`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.843 | +0.080 | 0.923 | Nauka programowania dla dzieci: Scratch | Mokotów | wto 20.10 17:00 | themes=Technologie |
| 2 | 0.591 | +0.080 | 0.671 | Warsztaty robotyki dla dzieci | Śródmieście | pon 19.10 11:00 | themes=Technologie |
| 3 | 0.528 | +0.000 | 0.528 | Poranek filmowy dla dzieci | Bielany | nie 25.10 10:00 | |
| 4 | 0.416 | +0.000 | 0.416 | Spektakl dla dzieci: Calineczka | Wilanów | nie 25.10 11:00 | |
| 5 | 0.382 | +0.000 | 0.382 | Planszówki w bibliotece | Ochota | nie 25.10 14:00 | |

`pokazano 5 | po filtrach 32/48 | odrzucone progiem 0.30: 23`

- ✅ Excellent — highest score of the whole run (0.923) when query terms overlap the tags.

## 9. „kolacja we dwoje”

`+ filtry: occasion=['Na randkę'], time_of_day=['wieczór']`

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.650 | +0.060 | 0.710 | Kolacja degustacyjna kuchni włoskiej | Śródmieście | sob 24.10 19:00 | occasion=Na randkę, time_of_day=wieczór |
| 2 | 0.484 | +0.060 | 0.544 | Degustacja win gruzińskich | Śródmieście | czw 22.10 19:00 | occasion=Na randkę, time_of_day=wieczór |
| 3 | 0.484 | +0.030 | 0.514 | Warsztaty gotowania dla dorosłych | Mokotów | sob 24.10 18:00 | time_of_day=wieczór |
| 4 | 0.509 | −0.040 | 0.469 | Targ śniadaniowy | Żoliborz | sob 24.10 09:00 | |
| 5 | 0.389 | +0.060 | 0.449 | Kino plenerowe: klasyka romansu | Śródmieście | sob 24.10 21:00 | occasion=Na randkę, time_of_day=wieczór |

`pokazano 5 | po filtrach 48/48 | odrzucone progiem 0.30: 37`

- ✅ Clean.
- ✅ #4 shows the time penalty working: 09:00 market demoted 0.509 → 0.469.

## 10. „coś ciekawego”

| # | cos | boost | score | tytuł | dzielnica | termin | matched |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 0.424 | +0.000 | 0.424 | Pokazy naukowe dla rodzin | Śródmieście | nie 25.10 13:00 | |
| 2 | 0.406 | +0.000 | 0.406 | Nocne zwiedzanie zoo | Praga-Północ | sob 24.10 19:00 | |
| 3 | 0.400 | +0.000 | 0.400 | Improwizacja teatralna: wieczór otwarty | Praga-Południe | pią 23.10 19:00 | |
| 4 | 0.400 | +0.000 | 0.400 | Wykład: nocne niebo nad Warszawą | Bemowo | sob 24.10 19:00 | |
| 5 | 0.398 | +0.000 | 0.398 | Wieczór kabaretowy | Ochota | czw 22.10 20:00 | |

`pokazano 5 | po filtrach 48/48 | odrzucone progiem 0.30: 27`

- ⚠️ The floor cannot discriminate: all candidates sit within 0.026 of each other
  (0.398–0.424). Vague queries need expansion or a popularity prior, not a threshold.

---

## Scoreboard

| # | prompt | verdict |
|---:|---|---|
| 1 | koncert jazzowy w sobotę | ✅ #1 correct · ❌ date ignored |
| 2 | coś na randkę wieczorem | ✅ good · ⚠️ unmatched zoo beats matched salsa |
| 3 | coś dla dziecka | ❌ kids-tagged events missing |
| 4 | darmowe warsztaty dla dorosłych | ❌ **kids course #1, seniors #3** |
| 5 | wystawa sztuki nowoczesnej | ✅ best of the run (0.812) |
| 6 | sport na świeżym powietrzu rano | ✅ top-2 · ❌ indoor gym #3 |
| 7 | coś spokojnego dla seniora | ⚠️ generic tail |
| 8 | nauka programowania dla dzieci | ✅ best score (0.923) |
| 9 | kolacja we dwoje | ✅ clean |
| 10 | coś ciekawego | ⚠️ floor can't discriminate |

**Solid: 5/10 · broken: 3/10 · weak: 2/10**

## What this run points at

1. **`BOOSTS["audience"] = 0.05` (+ 0.02 for the family tag)** — a matching audience
   currently earns nothing, which is why explicitly-tagged kids/senior events lose to
   generic family events. Fixes prompts 3 and 7.
2. **`PENALTIES["setting_mismatch"] = 0.04`** — same pattern as the existing
   time/audience/online penalties. Fixes prompt 6.
3. **LLM constraint extraction** — „w sobotę", „dla dorosłych", „nie za drogo" are all
   silently dropped today. Biggest single gap; fixes prompts 1, 2 and 4.
4. **Hub events persist** — *Planszówki w bibliotece* and *Nocne zwiedzanie zoo* each
   appear in 4 of 10 prompts. IDF/BM25 weighting remains the right cure.

## Caveat

All of this is measured on 48 hand-written events, not the real ~1200. Numbers move —
point the demo at a real snapshot (`--dump` / `EVENTS_FILE`) and re-run before acting on
any threshold.
