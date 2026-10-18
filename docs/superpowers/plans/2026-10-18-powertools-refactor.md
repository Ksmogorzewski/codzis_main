# Refaktor API na Powertools — plan wykonania

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** client-api i API partnera na routerze, loggerze i obsłudze wyjątków Powertools oraz schematach Pydantic — bez żadnej zmiany kontraktu HTTP.

**Architecture:** `codzis_common` dostaje fabrykę aplikacji Powertools (logger z correlation id, handlery `ApiError`/`ValidationError`/`Exception`, linia dostępu, wspólny format błędów). Każde API to `handler.py` składający `Router`-y z `routes/<domena>.py`; modele Pydantic w `schemas.py` każdego API. Logika domenowa (`events.py`, `store.py`, `friends.py`, `onboarding.py`, `account.py`, `payments.py`) zostaje — trasy ją wołają.

**Tech Stack:** Python 3.13, aws-lambda-powertools v3 (warstwa AWS), Pydantic v2, boto3, pytest + moto, Terraform.

**Spec:** `docs/superpowers/specs/2026-10-18-powertools-refactor-design.md`

## Global Constraints
- Gałąź `refactor/powertools`. W root `AGENTS.md` jest cudza niezacommitowana zmiana — stage'ować tylko własne hunki (`git add -p` albo `git apply --cached`), nigdy całego pliku; nigdy `git add -A`. Nieśledzone `.playwright-mcp/`, `app/` — nie ruszać.
- Nie pushować, nie mergować, nie robić `terraform apply`, nie pisać do AWS. `terraform -chdir=infra fmt -check` i `validate` wolno.
- **Kontrakt HTTP bez zmian:** ścieżki, metody, statusy, kształt JSON i treść komunikatów błędów identyczne; istniejące asercje testów o odpowiedziach nie mogą się zmienić (wolno zmienić tylko budowanie zdarzenia/wywołanie w `conftest.py`, jeśli Powertools tego wymaga).
- Format błędów: `{"error": str, "fields"?: [str], "code"?: str, "requestId"?: str}`; nieprzewidziany wyjątek → `500 {"error": "Coś poszło nie tak. Spróbuj ponownie.", "requestId": <requestId API Gateway>}`.
- Logi: JSON przez Powertools `Logger`, `correlation_id` = requestId; jedna linia dostępu na żądanie (route, status, durationMs); 4xx WARNING (status + code), 5xx `logger.exception`. Nigdy body, claimów, e-maili, imion, lokalizacji, tokenów.
- Warstwa Powertools: `arn:aws:lambda:eu-central-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:39`; klienci AWS dalej przez `codzis_common.aws.AWS_CONFIG`.
- Nie ruszać: `src/recommender_api/`, `recommender/`, `src/dispatcher/`, `src/importer/`, `tagger/`, `src/frontend/client/**` (kod).
- Commity po polsku (`refactor(api): …`, `chore(infra): …`, `docs(agents): …`), zakończone pustą linią i `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. Złe body/query (zły typ, brak pola, nadmiarowe pole, pusty string) → ten sam 400 i ta sama lista `fields` co przed refaktorem. → Task 2/3: testy istniejące + `test_validation_errors_unchanged`.
2. Nieznana trasa i zła metoda → 404 `{"error": "Nie znaleziono"}` jak dziś (Powertools domyślnie zwraca własny 404/405). → Task 1 `test_not_found_shape`.
3. CORS: Powertools nie może dodawać własnych nagłówków CORS ani zmieniać `Content-Type` (CORS robi API Gateway). → Task 1 `test_response_headers_unchanged`.
4. Liczby z DynamoDB (`Decimal`) i polskie znaki serializują się jak dziś (`json_default`, `ensure_ascii`). → Task 1 `test_decimal_and_polish_serialization`.
5. API partnera (REST v1 `{proxy+}`, autoryzacja tokenem Google albo kluczem) — trasy `payments/{id}/confirm` itd. działają, a linia dostępu ukrywa id. → Task 3 testy istniejące.

---

### Task 1: Wspólna aplikacja Powertools w `codzis_common` + infra + zależności
**Files:** Modify `src/layers/common/python/codzis_common/http.py` (albo nowy `app.py`), `tests/layers/test_http.py`, `requirements-dev.txt`, `pyproject.toml` (mypy/ruff dla nowych modułów), `infra/lambda.tf`, `infra/client_api.tf`, `infra/layers.tf` (jeśli potrzebna warstwa Pydantic).
**Produces:** `create_app(resolver_cls) -> resolver` z podpiętymi handlerami wyjątków i linią dostępu; `logger: Logger`; `current_request_id(app) -> str`; `ApiError` bez zmian (sygnatura `ApiError(status, message, **extra)`); `validation_fields(e: pydantic.ValidationError) -> list[str]`; `response()`/`parse_body` zostają tylko jeśli dalej potrzebne.
- [ ] Testy (padają): `test_api_error_shape`, `test_unexpected_error_500_with_request_id`, `test_not_found_shape`, `test_response_headers_unchanged`, `test_decimal_and_polish_serialization`, `test_access_log_line` (JSON z route/status/durationMs/correlation_id, bez body).
- [ ] Implementacja; sprawdź, czy warstwa Powertools v3 zawiera Pydantic v2 (dokumentacja/`pip show` w obrazie nie jest dostępny — sprawdź w docs Powertools lub listingu warstwy); jeśli nie, dodaj warstwę z Pydantic (Terraform, jak `codzis_common`). Terraform: warstwa Powertools w `layers` obu Lambd (client-api, api), `POWERTOOLS_SERVICE_NAME` w env. `terraform fmt -check` + `validate`.
- [ ] `scripts/backend-check.sh` zielony; commit.

### Task 2: client-api na routerze i schematach
**Files:** `src/client_api/handler.py` (tylko złożenie), nowe `src/client_api/routes/{me,events,saves,friends}.py`, `src/client_api/schemas.py`, testy `tests/client_api/**` (asercje bez zmian; nowe testy walidacji).
**Consumes:** Task 1. **Produces:** te same trasy i odpowiedzi co dziś (lista tras: docstring obecnego `handler.py`).
- [ ] Testy nowe: `test_validation_errors_unchanged` (dla `GET /api/events`, `PUT /api/profile`, `POST /api/friends/invite`, `GET /api/events/stats`, `PUT /api/me`), `test_routes_registered` (wszystkie trasy z `infra/client_api.tf` mają handler).
- [ ] Przenieś trasy do routerów, wejście przez modele Pydantic (query/body/path, w tym `PATH_ID`), wyjście przez modele lub typowane słowniki; logika domenowa bez zmian.
- [ ] `scripts/backend-check.sh` zielony (wszystkie dotychczasowe testy bez zmiany asercji); commit(y).

### Task 3: API partnera na routerze i schematach
**Files:** `src/api/handler.py`, nowe `src/api/routes/{me,events,payments}.py`, `src/api/schemas.py`, `tests/api/**`.
**Consumes:** Task 1. Autoryzacja (token Google w `authorizer.claims` albo `apiKeyId`) i nazwa partnera jak dziś; linia dostępu z ukrytym id płatności.
- [ ] Testy nowe: walidacja `POST /events` i `POST /payments` z tymi samymi `fields`; nieznana trasa 404.
- [ ] Implementacja; `scripts/backend-check.sh` zielony; commit.

### Task 4: Zasady w `AGENTS.md`
**Files:** root `AGENTS.md` (tylko własny hunk), `src/frontend/AGENTS.md` (sekcja kontraktu).
- [ ] Backend: router Powertools + `Router` per domena, schematy Pydantic na wejściu/wyjściu, `create_app` z `codzis_common`, logger Powertools, jeden format błędów, dostęp do bazy w modułach domeny, klienci AWS z `AWS_CONFIG`, przepis „nowa trasa” krok po kroku (model → trasa w routerze → test → trasa w Terraformie).
- [ ] Front (skrót i odnośnik do `src/frontend/AGENTS.md`): TanStack Router/Query, Zod na granicach, hooki `use-*.query/mutation`, Tailwind 4 + shadcn, bez AI slop.
- [ ] Kontrakt: Pydantic (backend) i Zod (front) opisują te same kształty; zmiana kontraktu = obie strony + testy w tym samym PR; jeden format błędów.
- [ ] Zastąp sekcję „Logi i obsługa błędów (backend)” wersją Powertools; commit `docs(agents): …`.

## Kolejność
Task 1 → (Task 2 ∥ Task 3 w osobnych worktree) → Task 4 → przegląd całości → `terraform plan` (Claude) → decyzja Dawida o `apply` (zalecane po demo).
