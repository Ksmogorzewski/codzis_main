# codzis_main — WarsawNow (Warsaw Open Data Hackathon, wyzwanie 3)

Instrukcje dla agentów AI (Claude, Codex, Cursor, Copilot…) i ludzi. WarsawNow podpowiada, co robić w Warszawie: wydarzenia i zajęcia z otwartych danych miasta (dane.um.warszawa.pl) i od partnerów, dopasowane do profilu użytkownika. Produkcja: `portal.waw-out.pl` (klient), `partner.waw-out.pl` (organizatorzy).

**Pilnuj struktury i wzorców opisanych tu i w `src/frontend/AGENTS.md`.** Jeśli zmiana do nich nie pasuje, zatrzymaj się i zapytaj, zamiast tworzyć nowy wzorzec.

## Mapa repo
| Część | Gdzie | Technologia | Właściciel |
|---|---|---|---|
| Importer: API UM → schemat v1 → SQS | `src/importer/` | Python, ECS | Krzysztof |
| Tagger: DeepSeek → DynamoDB `codzis-events` | `run_task.py`, `tagger/` | Python, ECS | Krzysztof / Jeremi |
| API klienta: `/api/me` (+ `/api/me/photo`), `/api/onboarding`, `/api/profile`, Eksploruj i społeczność: `/api/events` (+ `/stats`, `/{id}`, `/{id}/save`, `/{id}/attendees`), `/api/popular` | `src/client_api/` | Python, Lambda (zip) | Krzysztof |
| Rekomender RAG: `/api/recommendations` | `src/recommender_api/`, `recommender/` | Python, Lambda (kontener) | Jeremi |
| API panelu partnera | `src/api/`, `src/dispatcher/` | Python, Lambda | Krzysztof |
| **Front** (portal klienta + panel partnera) | `src/frontend/` | React + TS (Vite) | Dawid (klient) — **`src/frontend/AGENTS.md`** |
| Infrastruktura | `infra/` | Terraform | Krzysztof |

Szczegóły uruchamiania i wdrożenia: `README.md`, `recommender/README.md`, `tagger/README.md`.

## Jak to działa
```
portal.waw-out.pl ─ CloudFront ─ S3 (src/frontend/dist/client + config.js z Terraforma)
     └─ HTTP API (API Gateway, JWT z Cognito) ─┬─ Lambda client-api ─ DynamoDB codzis-users
                                               └─ Lambda recommender ─ indeks w S3 (+ codzis-events) + DeepSeek
                                                                      └─ zapisane zestawy: codzis-recommendations
importer (ECS) ─ SQS ─ tagger (ECS) ─ DynamoDB codzis-events
```
- API Gateway sprawdza token Cognito **zanim** uruchomi Lambdę; kod dostaje gotowe `claims` (`claims["sub"]` = id użytkownika).
- Logowanie Google (włącza je sekret `codzis/google-oauth` w AWS Secrets Manager, `infra/client_auth.tf`): klienci w puli klientów (Hosted UI + PKCE, `src/frontend/shared/oauth.ts`), organizatorzy w osobnej puli partnerów (`infra/partner_auth.tf`, samoobsługa: konto Google = konto organizatora); REST API partnera sprawdza wtedy ID token w nagłówku `X-Id-Token` zamiast klucza API, a `_partner` w `src/api/handler.py` bierze `partnerId` = `sub`.
- Rekomender ma zimny start (model mpnet: kilkadziesiąt s): rozgrzewanie co 5 min, indeks przebudowywany co 30 min; front ponawia zapytanie przy 0/502/503/504.
- Rekomendacje liczą się w tle i są zapisywane per użytkownik (`codzis-recommendations`): dziś / jutro / weekend z góry (w nocy, po zapisie profilu, przy logowaniu), inny dzień i fraza przy pierwszym zapytaniu. GET odpowiada od razu z zapisu; `202 {"status": "preparing"}` = zestaw się liczy (front pyta ponownie), `"updating": true` = w tle liczy się nowsza wersja (front odświeża co 3 s).

## Jak shipujemy feature (kolejność)
1. **Opis** w issue/PR: co widzi użytkownik, jaka zmiana API (ścieżka, parametry, kształt odpowiedzi, błędy).
2. **Backend** (osobny PR albo pierwsze commity): zmiana **addytywna** — nowa trasa albo nowe pole; istniejących pól nie zmieniamy ani nie usuwamy (zepsułoby wdrożony front). Kontrakt opisany w docstringu handlera.
3. **Front:** schemat Zod w `src/frontend/client/lib/schemas.ts`, hook w `hooks/`, UI — wg `src/frontend/AGENTS.md`.
4. **Gotowe** po obu stronach (sekcje „Gotowe” niżej i w `src/frontend/AGENTS.md`).
5. **Wdrożenie:** najpierw backend (`terraform apply`, dla rekomendera też obraz), potem front (`scripts/build-frontend.sh` + `terraform apply`).
6. **Git:** gałąź `feat/<krótko>` albo `fix/<krótko>`, PR do `main`, bez pushowania na `main` bezpośrednio; commity po polsku (`feat(api): …`, `feat(portal): …`, `fix(…): …`).

## Backend w Pythonie (Lambdy) — wzorzec
Wzorcowy plik: `src/client_api/handler.py`. Nowy kod backendu pisz tak samo.

**Budowa handlera**
- Jedna Lambda = jeden obszar API. Wejście `handler(event, context)`; trasy rozdziela `match event.get("routeKey")` (`"GET /api/me"`, `"PUT /api/profile"`…), każda trasa to osobna funkcja (`get_me(claims)`, `put_profile(claims, body)`), na końcu `raise ApiError(404, "Nie znaleziono")`.
- Użytkownik: `claims = event["requestContext"]["authorizer"]["jwt"]["claims"]`, id = `claims["sub"]`. Tokenu nie weryfikujemy sami — robi to API Gateway.
- Body: `parse_body(event)` (JSON-obiekt albo 400). Odpowiedź: `response(status, body)` (JSON, `ensure_ascii=False`, `Decimal` → int/float przez `json_default`). Nagłówki CORS dodaje API Gateway — nie dopisuj ich w kodzie.
- **Wspólny kod: warstwa `codzis_common`** (`src/layers/common/python/codzis_common/`, import `from codzis_common.http import ApiError, parse_body, response, now_iso`). Wdrażana jako Lambda Layer (`infra/layers.tf`, podpięta do client-api i API partnera). Nowy helper używany przez więcej niż jedną Lambdę dodaj tam (tylko biblioteka standardowa) z testem w `tests/layers/`, zamiast kopiować; nowa Lambda, która go używa, potrzebuje `layers = [aws_lambda_layer_version.common.arn]`. Rekomender ma własne kopie.
- **Błędy:** `raise ApiError(status, "komunikat po polsku", **extra)` → `{"error": "…", "fields"?: [...], "code"?: "…"}`. Kody: 400 (walidacja; `fields` = lista id błędnych pól), 404, 409 (np. `code: "needs_onboarding"`), 503 (zależność niedostępna). 401 zwraca API Gateway.
- **Logika osobno od HTTP:** czyste funkcje w osobnym module (jak `onboarding.py`: `validate_answers` zwraca `(czyste_dane, błędy)`, `compute_preferences`, `rag_profile`). Handler tylko łączy: wejście → logika → DynamoDB → odpowiedź.
- **API klienta** (`src/client_api/`): `handler.py` (routing + łączenie), `onboarding.py` (ankieta), `events.py` (rekord v1 → karta, okna czasu, filtry Eksploruj, kopia `next_slot` z rekomendera, pamięć scanu), `store.py` (DynamoDB: wydarzenia, zapisy, liczniki). Kontrakt tras w docstringu `handler.py`.
- **API partnera** (`src/api/`): `handler.py` (tylko routing), `events.py` (ogłoszenia i walidacja), `payments.py` (płatności), `store.py` (klienty AWS, transakcje, kredyty), `config.py` (zmienne środowiskowe).
- **Konfiguracja** z `os.environ[...]` (ustawia Terraform), czytana raz na poziomie modułu (np. `USERS_TABLE`, `DISTRICTS`). Klienty AWS (`boto3.resource("dynamodb").Table(...)`) też na poziomie modułu — przeżywają między wywołaniami.

**DynamoDB w kodzie**
- Odczyt/zapis po kluczu: `get_item`, `put_item`, `update_item` z `UpdateExpression` i `ExpressionAttributeValues`; `if_not_exists(createdAt, :now)` dla pól ustawianych raz; `ReturnValues="ALL_NEW"`, gdy zwracamy rekord.
- Liczby wracają jako `Decimal` (serializuje `json_default` z `codzis_common.http`); `None` i puste wartości nie są zapisywane (tagger ma `sanitize()`).
- **Bez `scan` w ścieżce żądania** (wolne i drogie przy wzroście) — wyjątki w tle: budowa indeksu rekomendera i nocne przeliczenie zestawów (`codzis-users`). Świadomy wyjątek w żądaniu: client-api (Eksploruj, Popularne) czyta `codzis-events` scanem z pamięcią w kontenerze Lambdy na 5 min (`EventCache` w `src/client_api/events.py`, ~1200 rekordów); liczniki zawsze z bazy. Docelowo GSI po czasie.
- Każda tabela ma jednego właściciela, który do niej zapisuje (sekcja „Dane”).

**Recepta: nowa trasa w API klienta**
1. `src/client_api/handler.py`: funkcja trasy + `case "GET /api/<x>":` w `match`; logika w osobnym module, jeśli to więcej niż kilka linii; docstring na górze pliku uzupełniony o trasę.
2. `infra/client_api.tf`: dopisz trasę do `for_each = toset([...])` (zasób tras ~linia 121); nowe uprawnienie (np. `dynamodb:GetItem` na `aws_dynamodb_table.events`) w `aws_iam_role_policy.client_api`; nowa zmienna w `environment.variables`.
3. Kod pakuje Terraform (`archive_file` z `src/client_api`) przy `terraform apply`.
4. **Zależności:** Lambda zip ma tylko bibliotekę standardową + `boto3`. Nowa biblioteka zewnętrzna = pytanie do Krzysztofa (trzeba ją spakować albo dać warstwę).
5. Front: schemat + hook (patrz `src/frontend/AGENTS.md`).

**Rekomender** (`src/recommender_api/`, logika w `recommender/`): Lambda z obrazu kontenera (model + torch). Zmiana kodu = `scripts/push-images.sh recommender` + `terraform apply`; przebudowa indeksu teraz: `scripts/recommender-refresh.sh`. Zapisane zestawy: `results_store.py` (claim liczenia, TTL); zmiana modelu, logiki rankingu lub kart = podbij `RESULTS_VERSION` (zapisane zestawy pokazują się dalej i przeliczają w tle); zmiana modelu (`DEFAULT_MODEL` = `EMBEDDING_MODEL_NAME` w Dockerfile) = też pełny reindeks zaraz po wdrożeniu obrazu (`scripts/recommender-refresh.sh`). LLM (rozwijanie frazy, ranking) tylko w fazie 2 liczenia w tle — nigdy w ścieżce GET. Pola karty określa `src/recommender_api/present.py`, pola w indeksie `FIELDS` w `index_store.py` — nowe pole na karcie wymaga obu i przebudowy indeksu. Ranking LLM ma timeout; przy błędzie uzasadnienie składają reguły — nie usuwaj tej ścieżki awaryjnej.

**Testy i kontrola backendu:** `scripts/backend-check.sh` (ruff check + format, mypy, pytest; raz: `python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`). Testy w `tests/`: `client_api/` (onboarding + handler), `api/` (handler partnera), `layers/` (`codzis_common`), `recommender/` (pipeline rekomendera na atrapie modelu, bez torcha; z prawdziwym modelem: `RUN_MODEL_TESTS=1` i pełne `recommender/requirements.txt`). Handler wołamy z ręcznie złożonym `event` na atrapach AWS z `moto` (fixture'y w `conftest.py` każdego katalogu) — nigdy na prawdziwym AWS. Ruff i mypy obejmują na razie tylko `src/client_api`, `src/api`, `src/dispatcher`, `src/layers` i `tests` (bez `tests/recommender/`, jak `recommender/`).

**Gotowe (backend):** zmiana addytywna; trasa w `handler.py` i w `infra/client_api.tf`; uprawnienia IAM tylko te potrzebne; komunikaty błędów po polsku; `scripts/backend-check.sh` przechodzi; `terraform plan` bez niespodzianek; front zaktualizowany w tym samym PR albo zaraz po.

## Dane
- **Kontrakt:** rekord wydarzenia „schemat v1” (`src/importer/schema.py`), taksonomia tagów (`tagger/prompt.py`), kroki ankiety (`src/client_api/onboarding.py` — dodanie pytania nie wymaga zmian we froncie), karta rekomendacji (`src/recommender_api/present.py`). Front odwzorowuje je w `src/frontend/client/lib/schemas.ts`.
- **Tabele (DynamoDB) i jedyny zapisujący:** `codzis-events` — tagger (TTL `expiresAt` sam usuwa zakończone); `codzis-users` (klucz `userId` = `sub`; dane konta w mapie `account`: data urodzenia, zdjęcie; imię i nazwisko z tokenu, niezmienne — `src/client_api/account.py`, zdjęcia w buckecie zdjęć pod `photos/avatars/`) — client-api; `codzis-recommendations` (`userId` + `setKey`, TTL `expiresAt`) — rekomender; `codzis-attendance` (zapisy „idę”: `eventId` + `userId`, `name` = imię z tokenu, `savedAt`; GSI `byUser`; PITR) i `codzis-event-stats` (licznik `saves` per `eventId`, `kind = "event"`; GSI `bySaves`) — client-api, zawsze razem w jednej transakcji; dane testowe (`scripts/seed_demo.py`) tylko z `seed: true` (`userId` = `seed-<n>`), usuwalne w całości; zapisy na wygasłe wydarzenia zostają (analityka), przy odczycie je pomijamy; `submissions`, `partners` (`partnerId` = `sub` z puli partnerów przy Google, inaczej `apiKeyId`), `payments` — API partnera.
- **API UM** (`POST https://dane.um.warszawa.pl/api/action/<akcja>`) nie ma historii ani stronicowania i **blokuje adresy IP AWS** — import uruchamiamy z laptopa (`scripts/import-local.sh`).

## Nowe dane w DynamoDB (decyzja zespołu: zostajemy przy DynamoDB, bez Postgresa)
1. **Zacznij od listy zapytań**, które funkcja musi obsłużyć („lista osób idących na wydarzenie X w dniu D”, „moje wydarzenia”), dopiero potem projektuj tabelę.
2. **Klucz pod najczęstsze zapytanie** (`PK` + opcjonalnie `SK` do sortowania, np. `eventId#dzień` + `userId`, `rozmowa` + `czas`); drugie zapytanie = GSI (np. po `userId`). Każde zapytanie to `get_item` / `query` po kluczu lub GSI.
3. **Bez `scan` w ścieżce żądania.** Liczniki („ile osób idzie”) aktualizuj atomowo przy zapisie (`ADD count :one`), nie licz przy odczycie.
4. **Dane powielone dla wygody** (np. tytuł wydarzenia w rekordzie deklaracji) opisz w docstringu i aktualizuj w jednym miejscu kodu.
5. **Raporty i analityka** (zliczenia po wielu polach) — nie w DynamoDB: eksport tabeli do S3 i zapytania SQL w Athenie.
6. **Nowa tabela = Terraform** (`PAY_PER_REQUEST`, `point_in_time_recovery` dla danych, których nie da się odtworzyć, TTL gdy dane wygasają) + jeden właściciel, który do niej zapisuje (dopisz do sekcji „Dane”).

## Bezpieczeństwo
- Sekrety (`WARSAW_API_TOKEN`, klucz DeepSeek, klucze AWS) tylko w `.env` (w `.gitignore`) albo w SSM; klient OAuth Google w AWS Secrets Manager (`codzis/google-oauth`, Terraform go tylko czyta). `config.js` frontu zawiera tylko dane publiczne (adres API, id puli i klienta Cognito).
- Nigdy sekretów, tokenów ani danych osobowych w kodzie, logach, commitach ani na czacie. W logach Lambd bez treści żądań i lokalizacji użytkownika.

## Zakres
Działające demo ważniejsze niż kompletność.
