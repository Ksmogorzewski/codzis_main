# codzis_main — WarsawNow (Warsaw Open Data Hackathon, wyzwanie 3)

Instrukcje dla agentów AI (Claude, Codex, Cursor, Copilot…) i ludzi. WarsawNow podpowiada, co robić w Warszawie: wydarzenia i zajęcia z otwartych danych miasta (dane.um.warszawa.pl) i od partnerów, dopasowane do profilu użytkownika. Produkcja: `portal.waw-out.pl` (klient), `partner.waw-out.pl` (organizatorzy).

**Pilnuj struktury i wzorców opisanych tu i w `src/frontend/AGENTS.md`.** Jeśli zmiana do nich nie pasuje, zatrzymaj się i zapytaj, zamiast tworzyć nowy wzorzec.

## Mapa repo
| Część | Gdzie | Technologia | Właściciel |
|---|---|---|---|
| Importer: API UM → schemat v1 → SQS | `src/importer/` | Python, ECS | Krzysztof |
| Tagger: DeepSeek → DynamoDB `codzis-events` | `run_task.py`, `tagger/` | Python, ECS | Krzysztof / Jeremi |
| API klienta: `/api/me` (+ `/api/me/photo`), `/api/onboarding`, `/api/profile`, Eksploruj i społeczność: `/api/events` (+ `/stats`, `/{id}`, `/{id}/save`, `/{id}/attendees`, `/{id}/crew` + `/messages`), `/api/popular`, `/api/me/crews` | `src/client_api/`: `handler.py` (składa aplikację), `routes/` (trasy per domena), `schemas.py` (Pydantic), `profiles.py`, moduły domeny | Python, Lambda (zip) + Powertools | Krzysztof |
| Rekomender RAG: `/api/recommendations` | `src/recommender_api/`, `recommender/` | Python, Lambda (kontener) | Jeremi |
| API panelu partnera | `src/api/`: `routes/` (`current_partner` w `routes/__init__.py`), `schemas.py`; `src/dispatcher/` | Python, Lambda + Powertools | Krzysztof |
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
- Logowanie Google (włącza je sekret `codzis/google-oauth` w AWS Secrets Manager, `infra/client_auth.tf`): klienci w puli klientów (Hosted UI + PKCE, `src/frontend/shared/oauth.ts`), organizatorzy w osobnej puli partnerów (`infra/partner_auth.tf`, samoobsługa: konto Google = konto organizatora); REST API partnera sprawdza wtedy ID token w nagłówku `X-Id-Token` zamiast klucza API, a `current_partner` w `src/api/routes/__init__.py` bierze `partnerId` = `sub`.
- Czat ekipy (`src/client_api/crews.py`): zapisani łączą się w ekipy do 4 osób; bez WebSocketów - front odpytuje `GET /api/events/{id}/crew?after=` co 3 s przy otwartym czacie i `GET /api/me/crews` (plakietki) co 30 s. Komunikaty Wodzireja tylko z danych wydarzenia, bez LLM.
- Rekomender ma zimny start (model mpnet: kilkadziesiąt s): rozgrzewanie co 5 min, indeks przebudowywany co 30 min; front ponawia zapytanie przy 0/502/503/504.
- Rekomendacje liczą się w tle i są zapisywane per użytkownik (`codzis-recommendations`): dziś / jutro / weekend z góry (w nocy, po zapisie profilu, przy logowaniu), inny dzień i fraza przy pierwszym zapytaniu. GET odpowiada od razu z zapisu; `202 {"status": "preparing"}` = zestaw się liczy (front pyta ponownie), `"updating": true` = w tle liczy się nowsza wersja (front odświeża co 3 s).

## Jak shipujemy feature (kolejność)
1. **Opis** w issue/PR: co widzi użytkownik, jaka zmiana API (ścieżka, parametry, kształt odpowiedzi, błędy).
2. **Backend** (osobny PR albo pierwsze commity): zmiana **addytywna** — nowa trasa albo nowe pole; istniejących pól nie zmieniamy ani nie usuwamy (zepsułoby wdrożony front). Kontrakt: model w `schemas.py` + opis w docstringu `handler.py`.
3. **Front:** schemat Zod w `src/frontend/client/lib/schemas.ts`, hook w `hooks/`, UI — wg `src/frontend/AGENTS.md`.
4. **Gotowe** po obu stronach (sekcje „Gotowe” niżej i w `src/frontend/AGENTS.md`).
5. **Wdrożenie:** najpierw backend (`terraform apply`, dla rekomendera też obraz), potem front (`scripts/build-frontend.sh` + `terraform apply`).
6. **Git:** gałąź `feat/<krótko>` albo `fix/<krótko>`, PR do `main`, bez pushowania na `main` bezpośrednio; commity po polsku (`feat(api): …`, `feat(portal): …`, `fix(…): …`).

## Backend w Pythonie (Lambdy) — wzorzec
Wzorzec: `src/client_api/` (`handler.py` + `routes/` + `schemas.py`). Nowy kod backendu pisz tak samo; API partnera (`src/api/`) jest zbudowane identycznie.

**Budowa API (AWS Lambda Powertools)**
- **`handler.py` tylko składa aplikację:** `app = create_app(APIGatewayHttpResolver)` z `codzis_common.app` (API partnera: `APIGatewayRestResolver`), `app.include_router(...)` dla routerów z `routes/`, `handler(event, context)` = `app.resolve(event, context)`. Kontrakt tras (ścieżki, kształty, błędy) w docstringu `handler.py`.
- **Jedna domena = jeden `Router` w `routes/<domena>.py`** (`router = APIGatewayHttpRouter()`, w API partnera `APIGatewayRouter()`), trasy `@router.get("/api/events/<id>")`. Parametry ścieżki nazywaj jak w API Gateway (`<id>`, `<userId>`), wtedy log pokazuje `GET /api/events/{id}`. Trasa zwraca `dict` (200) albo `(dict, 201)` albo model Pydantic. Pomocniki tras: client-api `routes/common.py` (`claims`, `body`, `query`, `path_id`, `now`), partner `routes/__init__.py` (`current_partner`).
- **Modele Pydantic w `schemas.py`** (body, query, parametry ścieżki; wyjście, gdy pomaga). `parse_input(Model, dane, "komunikat")` to **jedyna droga do 400 z `fields`** (wyjątek: formularz partnera z regułami między polami — `parse_event` / `parse_payment` w `src/api/schemas.py` same zamieniają `ValidationError` na `ApiError` przez `validation_fields`); `ValidationError` poza tym = nasze dane nie pasują do modelu → 500. Body przez `parse_body(router.current_event.raw_event)` z `codzis_common.http` (zły JSON → 400), nie `json_body` Powertools. Bez `enable_validation` i `cors=` w Powertools (dałyby 422 i nagłówki, które dodaje API Gateway).
- **Użytkownik:** claims z `requestContext.authorizer.jwt.claims` (`routes.common.claims`), id = `claims["sub"]`. Tokenu nie weryfikujemy sami — robi to API Gateway.
- **Logika i DynamoDB w modułach domeny, nie w trasach.** Trasa tylko łączy: wejście (model) → funkcja domeny → odpowiedź. Client-api: `profiles.py` (profil, logowanie, zapis ankiety), `onboarding.py` (ankieta: `validate_answers` → `(czyste_dane, błędy)`), `account.py` (dane konta, zdjęcie), `events.py` (rekord v1 → karta, okna czasu, filtry Eksploruj, pamięć scanu), `store.py` (wydarzenia, zapisy, liczniki), `friends.py`, `crews.py` (ekipy i czat: dołączanie, wiadomości, nieprzeczytane, wyjście). Partner: `events.py` (ogłoszenia), `payments.py`, `store.py` (klienty AWS, rekord partnera, transakcje, kredyty), `config.py` (zmienne środowiskowe).
- **Wspólny kod: warstwa `codzis_common`** (`src/layers/common/python/codzis_common/`: `app.py` — aplikacja, logger, błędy; `http.py` — `ApiError`, `parse_body`, `now_iso`, `json_default`; `aws.py` — `AWS_CONFIG`), Lambda Layer z `infra/layers.tf`. **`codzis_common` wymaga warstwy Powertools** (z Pydantic): Lambda, która go używa, ma `layers = [aws_lambda_layer_version.common.arn, local.powertools_layer_arn]` (ARN w `infra/layers.tf`; wersje w `requirements-dev.txt` zgodne z warstwą) i `POWERTOOLS_SERVICE_NAME`. Helper dla więcej niż jednej Lambdy dodaj tam z testem w `tests/layers/`, zamiast kopiować. Rekomender ma własne kopie.
- **Konfiguracja** z `os.environ[...]` (ustawia Terraform), czytana raz na poziomie modułu (np. `USERS_TABLE`, `DISTRICTS`). Klienty AWS też na poziomie modułu — przeżywają między wywołaniami.

**Błędy i logi (backend)**
- **Jeden format błędu:** `{"error": "komunikat po polsku", "fields"?: [...], "code"?: "…", "requestId"?: "…"}`. `raise ApiError(status, "komunikat", **extra)`: 400 (walidacja; `fields` = id błędnych pól), 404, 409 (np. `code: "needs_onboarding"`), 503 (zależność niedostępna). Każdy inny wyjątek `create_app` loguje z tracebackiem i zwraca `500 {"error": "Coś poszło nie tak. Spróbuj ponownie.", "requestId"}`; nieznana trasa albo metoda → `404 {"error": "Nie znaleziono"}`; 401 zwraca API Gateway. W trasach bez `print` i własnych `try/except Exception`.
- **Logger Powertools** (`from codzis_common.app import logger`, JSON w CloudWatch): każda linia ma `correlation_id` = requestId API Gateway, ten sam co w odpowiedzi 500. Logs Insights: `filter correlation_id = "<requestId>"`.
- **Jedna linia dostępu na żądanie** (`"message": "access"`): `route` (szablon, np. `GET /api/events/{id}`; nieznana trasa `GET (unmatched)` — nigdy identyfikatory z adresu), `status`, `durationMs`; 4xx dodatkowo WARNING `api_error` ze statusem i `code`, 5xx — ERROR.
- **Nigdy w logach:** body żądań, claims, e-maile, imiona, lokalizacje, tokeny (także `str(e)` błędu walidacji — zawiera wejście).
- **Klienty AWS:** każdy `boto3.client` / `boto3.resource` z `config=AWS_CONFIG` (`codzis_common.aws`: connect 1 s, read 3 s, maks. 2 próby `standard` — mieści się w 10 s Lambdy); własne opcje przez `AWS_CONFIG.merge(Config(...))`.

**DynamoDB w kodzie**
- Odczyt/zapis po kluczu: `get_item`, `put_item`, `update_item` z `UpdateExpression` i `ExpressionAttributeValues`; `if_not_exists(createdAt, :now)` dla pól ustawianych raz; `ReturnValues="ALL_NEW"`, gdy zwracamy rekord.
- Liczby wracają jako `Decimal` (serializuje `json_default` z `codzis_common.http`); `None` i puste wartości nie są zapisywane (tagger ma `sanitize()`).
- **Bez `scan` w ścieżce żądania** (wolne i drogie przy wzroście) — wyjątki w tle: budowa indeksu rekomendera i nocne przeliczenie zestawów (`codzis-users`). Świadomy wyjątek w żądaniu: client-api (Eksploruj, Popularne) czyta `codzis-events` scanem z pamięcią w kontenerze Lambdy na 5 min (`EventCache` w `src/client_api/events.py`, ~1200 rekordów); liczniki zawsze z bazy. Docelowo GSI po czasie.
- Każda tabela ma jednego właściciela, który do niej zapisuje (sekcja „Dane”).

**Recepta: nowa trasa** (client-api; w API partnera tak samo w `src/api/`, ścieżki względem stage'a (`/me`), bez kroku 4 — REST API ma jedno proxy `/{proxy+}`)
1. **Schemat:** model wejścia w `schemas.py` (Pydantic), komunikat błędu po polsku.
2. **Trasa** w routerze domeny `routes/<domena>.py` (nowa domena = nowy plik z `router` + `app.include_router` w `handler.py`): wejście przez `parse_input`, logika i DynamoDB w module domeny; opis trasy w docstringu `handler.py`.
3. **Test:** kontrakt (status, kształt odpowiedzi) i walidacja (komunikat, `fields`) — `tests/client_api/test_routes.py` (`test_routes_registered` pilnuje zgodności z Terraformem), partner: `tests/api/test_contract.py`.
4. **Terraform:** trasa w `for_each = toset([...])` zasobu `aws_apigatewayv2_route.client` w `infra/client_api.tf`; nowe uprawnienie IAM w `aws_iam_role_policy.client_api`, nowa zmienna w `environment.variables`. Kod pakuje `archive_file` przy `terraform apply`.
5. **`AGENTS.md`:** ścieżka w wierszu API w „Mapa repo”.
6. **Front:** schemat Zod + hook (sekcja „Spójność backend ↔ front”).

**Zależności:** zip Lambdy = biblioteka standardowa + `boto3`; Powertools i Pydantic z warstwy. Nowa biblioteka zewnętrzna = pytanie do Krzysztofa.

**Rekomender** (`src/recommender_api/`, logika w `recommender/`): Lambda z obrazu kontenera (model + torch). Zmiana kodu = `scripts/push-images.sh recommender` + `terraform apply`; przebudowa indeksu teraz: `scripts/recommender-refresh.sh`. Zapisane zestawy: `results_store.py` (claim liczenia, TTL); zmiana modelu, logiki rankingu lub kart = podbij `RESULTS_VERSION` (zapisane zestawy pokazują się dalej i przeliczają w tle); zmiana modelu (`DEFAULT_MODEL` = `EMBEDDING_MODEL_NAME` w Dockerfile) = też pełny reindeks zaraz po wdrożeniu obrazu (`scripts/recommender-refresh.sh`). LLM (rozwijanie frazy, ranking) tylko w fazie 2 liczenia w tle — nigdy w ścieżce GET. Pola karty określa `src/recommender_api/present.py`, pola w indeksie `FIELDS` w `index_store.py` — nowe pole na karcie wymaga obu i przebudowy indeksu. Ranking LLM ma timeout; przy błędzie uzasadnienie składają reguły — nie usuwaj tej ścieżki awaryjnej.

**Testy i kontrola backendu:** `scripts/backend-check.sh` (ruff check + format, mypy, pytest; raz: `python3.13 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`). Testy w `tests/`: `client_api/` (onboarding, handler; trasy i walidacja: `test_routes.py`), `api/` (handler partnera, kontrakt: `test_contract.py`), `layers/` (`codzis_common`), `recommender/` (pipeline rekomendera na atrapie modelu, bez torcha; z prawdziwym modelem: `RUN_MODEL_TESTS=1` i pełne `recommender/requirements.txt`). Handler wołamy z ręcznie złożonym `event` na atrapach AWS z `moto` (fixture'y w `conftest.py` każdego katalogu) — nigdy na prawdziwym AWS. Ruff i mypy obejmują na razie tylko `src/client_api`, `src/api`, `src/dispatcher`, `src/layers` i `tests` (bez `tests/recommender/`, jak `recommender/`).

**Gotowe (backend):** zmiana addytywna; model w `schemas.py`, trasa w `routes/` i w `infra/client_api.tf`, test kontraktu i walidacji; uprawnienia IAM tylko te potrzebne; komunikaty błędów po polsku; `scripts/backend-check.sh` przechodzi; `terraform plan` bez niespodzianek; front zaktualizowany w tym samym PR albo zaraz po.

## Spójność backend ↔ front
- **Jeden kontrakt, dwa opisy:** modele Pydantic (`src/client_api/schemas.py`, `src/api/schemas.py`) i schematy Zod (`src/frontend/client/lib/schemas.ts`) opisują te same kształty. Zmiana kontraktu = obie strony + testy (pytest i vitest) w tym samym PR.
- **Jeden format błędu** `{error, fields?, code?, requestId?}` — czyta go `lib/api.ts` (komunikat, `fields`, `code`); nowy `code` = obsługa we froncie w tym samym PR.
- **Front** (szczegóły: **`src/frontend/AGENTS.md`**): TanStack Router (cienkie trasy plikowe) i TanStack Query (hooki `hooks/use-<x>.query.ts` / `use-<x>.mutation.ts`, bez `fetch` w komponentach), Zod na granicach (odpowiedzi API, search params), Tailwind 4 + shadcn/ui tylko przez tokeny motywu, bez „AI slop”.

## Dane
- **Kontrakt:** rekord wydarzenia „schemat v1” (`src/importer/schema.py`), taksonomia tagów (`tagger/prompt.py`), kroki ankiety (`src/client_api/onboarding.py` — dodanie pytania nie wymaga zmian we froncie), karta rekomendacji (`src/recommender_api/present.py`). Front odwzorowuje je w `src/frontend/client/lib/schemas.ts`.
- **Tabele (DynamoDB) i jedyny zapisujący:** `codzis-events` — tagger (TTL `expiresAt` sam usuwa zakończone); `codzis-users` (klucz `userId` = `sub`; dane konta w mapie `account`: data urodzenia (z niej przedział wieku `preferences.ageRange`, `onboarding.with_age`), zdjęcie; imię i nazwisko z tokenu, niezmienne — `src/client_api/account.py`, zdjęcia w buckecie zdjęć pod `photos/avatars/`) — client-api; `codzis-recommendations` (`userId` + `setKey`, TTL `expiresAt`) — rekomender; `codzis-attendance` (zapisy „idę”: `eventId` + `userId`, `name` = imię z tokenu, `savedAt`; GSI `byUser`; PITR) i `codzis-event-stats` (licznik `saves` per `eventId`, `kind = "event"`; GSI `bySaves`) — client-api, zawsze razem w jednej transakcji; dane testowe (`scripts/seed_demo.py`) tylko z `seed: true` (`userId` = `seed-<n>`), usuwalne w całości; zapisy na wygasłe wydarzenia zostają (analityka), przy odczycie je pomijamy; `codzis-crews` (ekipy, członkowie i wiadomości czatu: `eventId` + `sk`, opis w `crews.py`; TTL `expiresAt` 30 dni po końcu wydarzenia; PITR) — client-api, dołączenie / wiadomość / wyjście zawsze transakcją; `submissions`, `partners` (`partnerId` = `sub` z puli partnerów przy Google, inaczej `apiKeyId`), `payments` — API partnera.
- **API UM** (`POST https://dane.um.warszawa.pl/api/action/<akcja>`) nie ma historii ani stronicowania i **blokuje adresy IP AWS** — import uruchamiamy z laptopa (`scripts/import-local.sh`).

## Nowe dane w DynamoDB (decyzja zespołu: zostajemy przy DynamoDB, bez Postgresa)
1. **Zacznij od listy zapytań**, które funkcja musi obsłużyć („lista osób idących na wydarzenie X w dniu D”, „moje wydarzenia”), dopiero potem projektuj tabelę.
2. **Klucz pod najczęstsze zapytanie** (`PK` + opcjonalnie `SK` do sortowania, np. `eventId#dzień` + `userId`, `rozmowa` + `czas`); drugie zapytanie = GSI (np. po `userId`). Każde zapytanie to `get_item` / `query` po kluczu lub GSI.
3. **Bez `scan` w ścieżce żądania.** Liczniki („ile osób idzie”) aktualizuj atomowo przy zapisie (`ADD count :one`), nie licz przy odczycie.
4. **Dane powielone dla wygody** (np. tytuł wydarzenia w rekordzie deklaracji) opisz w docstringu i aktualizuj w jednym miejscu kodu.
5. **Raporty i analityka** (zliczenia po wielu polach) — nie w DynamoDB: eksport tabeli do S3 i zapytania SQL w Athenie.
6. **Nowa tabela = Terraform** (`PAY_PER_REQUEST`, `point_in_time_recovery` dla danych, których nie da się odtworzyć, TTL gdy dane wygasają) + jeden właściciel, który do niej zapisuje (dopisz do sekcji „Dane”).

## Bezpieczeństwo
- Sekrety (`WARSAW_API_TOKEN`, klucz DeepSeek, klucze AWS) tylko w `.env` (w `.gitignore`) albo w SSM; klient OAuth Google w AWS Secrets Manager (`codzis/google-oauth`: Terraform zakłada go z `CHANGE_ME`, wartość ustawiasz poza nim). `config.js` frontu zawiera tylko dane publiczne (adres API, id puli i klienta Cognito).
- Nigdy sekretów, tokenów ani danych osobowych w kodzie, logach, commitach ani na czacie. W logach Lambd bez treści żądań i lokalizacji użytkownika.

## Zakres
Działające demo ważniejsze niż kompletność.
