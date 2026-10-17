# Społeczność, Eksploruj i Popularne — projekt

Data: 2026-10-18 (noc przed demo). Właściciel: Dawid. Gałąź: `feat/community` (na `chore/backend-quality` — testy i warstwa `codzis_common`).

## Po co
Rekomendacje („Dla Ciebie”) dają szybką decyzję, ale gdy nic nie pasuje, użytkownik nie ma gdzie szukać, a aplikacja nie wie, co interesuje innych. Dokładamy trzy rzeczy: **Eksploruj** (przeglądanie wszystkiego, co się dzieje, bez filtra profilu), **Zapisz** (deklaracja „idę”, z licznikiem i listą zapisanych — fundament społeczności) i **Popularne w tym tygodniu** (wydarzenia z największą liczbą zapisów). Czat dla zapisanych robi Kacper — nasza tabela zapisów jest dla niego źródłem członków.

## Cele
- Nawigacja z czterema miejscami: **Dla Ciebie** (`/`), **Eksploruj** (`/eksploruj`), **Popularne** (`/popularne`), **Profil** (`/profil`). Na telefonie dolny pasek zakładek, na desktopie w nagłówku.
- Przycisk **Zapisz / Zapisano** na karcie i w szczegółach (przełącza), z licznikiem „Zapisanych: N”.
- W szczegółach wydarzenia **lista zapisanych** (imiona) i liczba.
- **Eksploruj:** wszystkie wydarzenia w oknie czasu (dziś / jutro / weekend / inny dzień), filtry: kategoria (Sport / Kultura / Rekreacja), dzielnica, tylko darmowe, pod dachem; wyszukiwarka; sortowanie po najbliższym starcie (lub odległości, gdy znana pozycja).
- **Popularne w tym tygodniu:** wydarzenia odbywające się w bieżącym tygodniu (pon–nd, Europe/Warsaw), posortowane po liczbie zapisanych, z licznikiem.
- **Imię** użytkownika: pole „Imię” przy rejestracji i w profilu; pokazywane na listach zapisanych (i w czacie Kacpra).
- **Dane testowe (seed)** na demo — patrz niżej.

## Nie-cele
- Czat (Kacper). Zapis na konkretny dzień wydarzenia wielodniowego (zapis dotyczy całego wydarzenia). Ekran „Moje zapisy” (stan „Zapisano” widać na kartach). Powiadomienia. Zmiany w rekomenderze (`src/recommender_api/`, `recommender/` — nie ruszamy).

## Anty-cele
- Pokazywanie e-maili innych użytkowników — **nigdy**; na listach tylko imię (brak imienia → „Ktoś”).
- Sztuczne dane mieszające się z prawdziwymi w sposób nieodwracalny — seed musi dać się w całości usunąć jednym poleceniem.
- Koszt LLM od danych testowych — seed nie może trafić do `codzis-users` (nocne przeliczanie rekomendacji objęłoby sztuczne osoby).

## Dane (DynamoDB, zasady z `AGENTS.md` → „Nowe dane w DynamoDB”)
Zapytania: (1) czy ja zapisałem się na X, (2) lista zapisanych na X, (3) liczba zapisanych na X (wiele wydarzeń naraz dla listy kart), (4) top wydarzeń po liczbie zapisanych.

- **`codzis-attendance`** — PK `eventId`, SK `userId`; pola: `name` (imię w chwili zapisu, kopia dla wygody), `savedAt` (ISO), opcjonalnie `seed: true`. Odpowiada na (1) `get_item` i (2) `query` po `eventId`. PITR włączony (dane użytkowników).
- **`codzis-event-stats`** — PK `eventId`; pola: `saves` (licznik, `ADD`), `kind = "event"` (stała pod GSI). GSI **`bySaves`**: PK `kind`, SK `saves` (Number) — (4) `query` malejąco z limitem. (3) = `batch_get_item` po `eventId`.
- **Zapis/wypisanie** atomowo transakcją (`TransactWriteItems`): Put attendance z warunkiem `attribute_not_exists(userId)` + Update stats `ADD saves :one` (wypisanie: Delete z warunkiem istnienia + `ADD saves :minus`). Ponowny zapis/wypisanie = brak zmiany (idempotentnie, bez błędu).
- Jedyny zapisujący obie tabele: **client-api** (oraz skrypt seed, tylko rekordy `seed`). Dopisać do sekcji „Dane” w `AGENTS.md`.
- **Wydarzenia dla Eksploruj/Popularne:** client-api czyta `codzis-events` przez `scan` z **pamięcią w module Lambdy (5 min)** i filtruje w Pythonie (~1200 rekordów). To świadomy wyjątek od zasady „bez scan w ścieżce żądania”, opisany w docstringu; docelowo indeks/GSI po czasie.

## API (client-api, zmiany addytywne; trasy z JWT jak dotąd)
| Trasa | Odpowiedź |
|---|---|
| `GET /api/events?when=today\|tomorrow\|weekend\|date&date=&cat=&district=&free=&indoor=&q=` | `{ window, items: Card[] }` (bez `reason`), każda karta z `saves` i `saved` (czy ja) |
| `GET /api/events/{id}` | karta + `text` (opis bez HTML), `occurrences`, `importedAt`, `saves`, `saved` — 404 gdy brak |
| `PUT /api/events/{id}/save` / `DELETE /api/events/{id}/save` | `{ saved, saves }` |
| `GET /api/events/{id}/attendees` | `{ saves, saved, people: [{ name, isMe }] }` (max 100, najnowsi najpierw) |
| `GET /api/popular` | wydarzenia z bieżącego tygodnia po `saves` malejąco: `{ window, items: Card[] }` (max 20) |

Karta (`Card`) ma ten sam kształt co karta rekomendacji z `src/recommender_api/present.py` (bez `reason`, `reasonSource`, `score`) + `saves`, `saved` — front używa jednego komponentu karty. Mapowanie rekordu v1 → karta w osobnym module client-api (np. `events.py`), z testami. Kategoria (`cat`) według tej samej mapy co front (`src/frontend/client/lib/categories.ts`). Dzielnice z `DISTRICTS`.

Rekomendacje (`/api/recommendations`) zostają bez zmian; front dociąga do ich kart `saves`/`saved` przez `GET /api/events/stats?ids=…` **albo** pokazuje licznik dopiero w szczegółach — do decyzji implementującego (mniejsza liczba zapytań wygrywa).

## Imię
- Rejestracja: pole „Imię” (wymagane) → atrybut Cognito `name` (`SignUp` `UserAttributes`). Imienia nie zmieniamy później (brak pola w profilu); wyjątek: jednorazowe uzupełnienie dla kont bez imienia (decyzja 2). `GET /api/me` już zapisuje `displayName` z claimu `name`.
- Zapis na wydarzenie kopiuje imię z claimu do `attendance.name`.

## Front (`src/frontend/client`, zasady z `src/frontend/AGENTS.md`)
- Trasy: `_app/eksploruj.tsx`, `_app/popularne.tsx` (+ istniejące). Filtry Eksploruj jako search params (Zod). Szczegóły korzystają z `GET /api/events/{id}` (pełny opis + `importedAt`), z dotychczasowym zapasem z cache rekomendacji.
- Hooki: `use-events.query.ts`, `use-event.query.ts`, `use-popular.query.ts`, `use-attendees.query.ts`, `use-save.mutation.ts` (optymistyczna zmiana licznika i stanu, rollback przy błędzie; po sukcesie unieważnij `attendees` i `popular`).
- Komponenty: wspólna karta z przyciskiem Zapisz i licznikiem; lista zapisanych w szczegółach; dolny pasek zakładek na telefonie.

## Seed (dane testowe na demo)
- Skrypt `scripts/seed_demo.py` (Python 3.13, boto3, uruchamiany lokalnie z kluczami AWS): tryby `--dry-run` (domyślny: pokazuje plan), `--apply`, `--delete` (usuwa **tylko** rekordy z `seed: true` i koryguje liczniki).
- Sztuczne osoby: `userId` = `seed-<n>`, polskie imiona, `seed: true`. **Nie** do `codzis-users`, **nie** do Cognito.
- Zapisy na prawdziwe wydarzenia z `codzis-events` odbywające się w bieżącym tygodniu; rozkład nierówny (kilka wydarzeń wyraźnie popularnych, długi ogon), żeby „Popularne” miało sens. Liczniki w `codzis-event-stats` spójne z zapisami (przez te same transakcje albo przeliczone na końcu).
- Idempotentny (ponowne `--apply` nie dubluje), deterministyczny (stałe ziarno losowania).

## Ograniczenia
- Deadline: kod zamrożony 07:00, demo 11:30. Wdrożenie backendu przez `terraform apply` (Krzysztof): nowe tabele, GSI, trasy, uprawnienia (`dynamodb:Scan` na events, Get/Put/Delete/Query/TransactWrite na nowych tabelach, `BatchGetItem` na stats). Najpierw backend, potem front.
- Testy: `scripts/backend-check.sh` (pytest + moto) dla nowych tras i logiki; vitest dla logiki frontu.

## Decyzje po przeglądzie (decyzje Claude, do sprawdzenia przez Dawida)
1. **Zajęcia cykliczne** (`kind=recurring`, `schedule`): client-api ma **własną kopię** logiki terminu (port `next_slot` z `recommender/retriever/filters.py` do modułu client-api, z testami; rekomendera nie ruszamy ani nie importujemy). Karta ma `slot` = najbliższy termin w oknie, liczony tak samo jak w rekomenderze. Zajęcia cykliczne są w Eksploruj, gdy mają termin w oknie; w Popularnych, gdy mają termin w bieżącym tygodniu i mają zapisy.
2. **Imię (decyzja Dawida: niezmienne):** podawane przy rejestracji (atrybut Cognito `name`), potem **nie da się go zmienić** w UI. Konta bez imienia (założone wcześniej) widzą **jednorazową** prośbę o imię przed pierwszym zapisem na wydarzenie: `UpdateUserAttributes` (tylko gdy `name` puste) + od razu odświeżenie tokenu (`REFRESH_TOKEN_AUTH`), żeby nowy ID token miał claim `name`. Pula nie definiuje własnego `schema`, więc standardowy `name` jest zapisywalny; Google wyłączone. Zapis na wydarzenie kopiuje imię z claimu.
3. **Lambda client-api:** pamięć 128 → **512 MB**, timeout 10 s zostaje. Pamięć podręczna wydarzeń per kontener (5 min) jest akceptowalna — różnice między kopiami trwają maks. 5 min. Liczniki (`saves`) zawsze z bazy, nie z pamięci.
4. **Popularne (od najwięcej zapisanych):** `query` GSI `bySaves` malejąco z zapasem (do 200), filtr do wydarzeń z terminem w bieżącym tygodniu, maks. 20. Tylko `saves > 0`. Gdy pusto — stan pusty „Jeszcze nikt się nie zapisał — bądź pierwszy” z linkiem do Eksploruj (bez dopełniania innymi wydarzeniami). Seed zapewnia treść na demo.
5. **Stabilność `eventId`:** id z importera to hash klucza źródła (`kal-…`, `spt-…`), stabilne między importami. Po wygaśnięciu wydarzenia (TTL) **zapisy zostają do analityki (decyzja Dawida)** — przy odczycie pomijamy wydarzenia, których nie ma; bez sprzątania.
6. **Terraform pisze implementujący** (tabele, GSI, IAM, trasy, `DELETE` w CORS `allow_methods` — dziś tylko GET/PUT/OPTIONS, `memory_size`); **wdraża Dawid** (`terraform plan` → `apply` → test) po przeniesieniu stanu Terraforma do S3 (backend `s3` z `use_lockfile`, migracja: Krzysztof). Bez ręcznych zmian przez AWS CLI (rozjazd ze stanem).

## Zostawione budowniczemu
Dokładny podział modułów client-api (`events.py`, `attendance.py`…), wygląd dolnego paska, liczba kart na stronie Eksploruj (stronicowanie albo limit), sposób dociągania liczników do kart rekomendacji (patrz wyżej).
