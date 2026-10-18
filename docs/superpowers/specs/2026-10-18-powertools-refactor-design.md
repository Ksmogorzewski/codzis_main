# Refaktor API na AWS Lambda Powertools — projekt

Data: 2026-10-18. Właściciel: Dawid. Gałąź: `refactor/powertools` (z `main` @ `1fb5038`, wszystko wdrożone).

## Po co
Backend API (client-api, API partnera) działa i jest przetestowany, ale routing to ręczny `match` w jednym pliku (`src/client_api/handler.py`: 543 linie, ~20 tras), walidacja wejścia jest pisana ręcznie w każdej trasie po swojemu, a logi i obsługa błędów to nasze własne helpery. Chcemy, żeby backend był pisany jak reszta stosu BV: router z modułami per domena (jak Hono w melange), schematy na granicach (jak Zod we froncie), jeden logger i jedno miejsce obsługi błędów — i żeby agenci zespołu pisali nowy kod w tym samym stylu.

## Cele (decyzje Dawida)
1. **Schematy wejścia i wyjścia (Pydantic v2)** dla każdej trasy: body, query i parametry ścieżki walidowane modelem; błąd walidacji → `400 {"error": "...", "fields": [...]}` jak dziś. Odpowiedzi budowane z modeli (albo przez nie walidowane) — kształt JSON **bez zmian**.
2. **Router Powertools** (`aws_lambda_powertools.event_handler`): client-api → `APIGatewayHttpResolver` (HTTP API v2), API partnera → `APIGatewayRestResolver` (REST API v1, `{proxy+}`). Trasy w plikach per domena (`Router`): client-api `routes/me.py` (me, profil, ankieta, zdjęcie), `routes/events.py` (Eksploruj, szczegóły, statystyki, popularne, moje), `routes/saves.py` (zapis/wypisanie, lista zapisanych), `routes/friends.py`; API partnera `routes/events.py`, `routes/payments.py`, `routes/me.py`. `handler.py` = tylko złożenie aplikacji.
3. **Logger i obsługa wyjątków z Powertools** zamiast `codzis_common.http.handle_request`: `Logger` (JSON, `correlation_id` = requestId API Gateway), `@app.exception_handler(ApiError)` i handler ogólny `Exception` (log `exception` + `500 {"error": "Coś poszło nie tak. Spróbuj ponownie.", "requestId"}`), linia dostępu per żądanie (route, status, durationMs, requestId) — zachowanie jak dziś.
4. **Zasady w `AGENTS.md`** (obowiązkowe dla agentów zespołu): spójna architektura backendu i frontu oraz kontrakt między nimi.

## Nie-cele
Idempotency, Metrics, Tracer, Parameters, repozytoria tabel, alarmy, zmiany w modelu danych, rekomender (`src/recommender_api/`, `recommender/`), dispatcher, importer, tagger, front (poza dokumentacją).

## Anty-cele
- **Żadnej zmiany kontraktu HTTP** (ścieżki, metody, kody, kształt JSON, komunikaty błędów, CORS). Front nie może zauważyć różnicy. Istniejące testy (364) przechodzą bez zmiany asercji o odpowiedziach — wolno zmieniać tylko sposób wywołania/budowy zdarzenia w testach.
- Żadnych nowych zależności w paczkach Lambd poza Powertools (i Pydantic, jeśli warstwa go nie zawiera).
- Nie logujemy treści żądań, claimów, e-maili, imion, lokalizacji, tokenów.

## Ograniczenia
- Powertools jako publiczna warstwa AWS: `arn:aws:lambda:eu-central-1:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:39` (Python 3.13, arm64). Pydantic v2: sprawdzić, czy warstwa go zawiera; jeśli nie — zbudować małą warstwę z Pydantic w Terraformie (jak `codzis_common`) albo dołączyć do zipa Lambdy; decyzja implementującego, opisana w PR.
- Testy lokalnie: `aws-lambda-powertools[parser]` (z Pydantic) w `requirements-dev.txt`, wersja zgodna z warstwą.
- `scripts/backend-check.sh` (ruff, mypy, pytest) zielony.
- Wdrożenie przez `terraform plan` (Claude) → `apply` (Dawid), najlepiej po demo.

## Zostawione budowniczemu
Dokładne nazwy modeli i modułów, czy wyjście walidować modelem czy tylko typować, sposób przekazania `claims` do tras (np. helper `current_claims()`), jak zachować kolejność walidacji pól i komunikaty 400 identyczne z dzisiejszymi.
