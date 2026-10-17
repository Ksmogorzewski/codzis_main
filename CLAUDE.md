# codzis_main — WarsawNow (Warsaw Open Data Hackathon, wyzwanie 3)

WarsawNow podpowiada, co robić w Warszawie: wydarzenia i zajęcia z otwartych danych miasta (dane.um.warszawa.pl) i od partnerów, dopasowane do profilu użytkownika. Produkcja: `portal.waw-out.pl` (klient), `partner.waw-out.pl` (organizatorzy).

## Mapa repo
| Część | Gdzie | Technologia | Właściciel | Instrukcje |
|---|---|---|---|---|
| Importer: API UM → schemat v1 → SQS | `src/importer/` | Python, ECS | Krzysztof | `README.md` |
| Tagger: DeepSeek → DynamoDB `codzis-events` | `run_task.py`, `tagger/` | Python, ECS | Krzysztof / Jeremi | `tagger/README.md` |
| API klienta: `/api/me`, `/api/onboarding`, `/api/profile` | `src/client_api/` | Python, Lambda | Krzysztof | `README.md` („Portal klienta”) |
| Rekomender RAG: `/api/recommendations` | `src/recommender_api/`, `recommender/` | Python, Lambda (kontener) | Jeremi | `recommender/README.md` |
| Panel partnera (API) | `src/api/`, `src/dispatcher/` | Python, Lambda | Krzysztof | `README.md` |
| **Front (portal klienta + panel partnera)** | `src/frontend/` | React + TS (Vite) | Dawid (klient) | **`src/frontend/CLAUDE.md`** |
| Infrastruktura | `infra/` | Terraform | Krzysztof | `README.md` |

## Jak to działa (skrót)
```
portal.waw-out.pl ─ CloudFront ─ S3 (src/frontend/dist/client + config.js z Terraforma)
     └─ HTTP API (API Gateway, JWT z Cognito) ─┬─ Lambda client-api ─ DynamoDB codzis-users
                                               └─ Lambda recommender ─ indeks S3 + codzis-events + DeepSeek
importer (ECS) ─ SQS ─ tagger (ECS) ─ DynamoDB codzis-events
```
- API Gateway sprawdza token Cognito **zanim** uruchomi Lambdę; kod dostaje gotowe `claims`.
- Rekomender ma zimny start (kilkanaście s): rozgrzewanie co 5 min, front ponawia zapytanie przy 0/502/503/504.

## Zasady wspólne
- **Kontrakt danych:** rekord wydarzenia „schemat v1” (`src/importer/schema.py`), taksonomia tagów (`tagger/prompt.py`), kroki ankiety (`src/client_api/onboarding.py`), karta rekomendacji (`src/recommender_api/present.py`). Front odwzorowuje je w `src/frontend/client/lib/schemas.ts`. **Zmiana kontraktu = informacja do zespołu i aktualizacja po obu stronach w tym samym PR.**
- **Każda tabela ma jednego właściciela, który do niej zapisuje:** `codzis-events` — tagger; `codzis-users` — client-api; `submissions`, `partners`, `payments` — API partnera.
- **Zmiany w backendzie addytywne:** nowe pola i trasy, nie zmiana istniejących — inaczej psujesz front.
- **Niczego nie zmyślamy.** Wszystko, co widzi użytkownik, pochodzi z API miasta albo od partnerów i ma źródło.
- **API UM** (`POST https://dane.um.warszawa.pl/api/action/<akcja>`) nie ma historii ani stronicowania i **blokuje adresy IP AWS** — import uruchamiamy z laptopa (`scripts/import-local.sh`).
- **Sekrety** (`WARSAW_API_TOKEN`, klucz DeepSeek, klucze AWS) tylko w `.env` (w `.gitignore`) albo w SSM. `config.js` frontu zawiera tylko dane publiczne (adres API, id puli i klienta Cognito). Nigdy sekretów w kodzie, logach, commitach ani na czacie.
- **Zakres:** działające demo ważniejsze niż kompletność. Nowa funkcja albo zależność = zgoda zespołu.
- **Git:** gałąź + PR do `main`, bez pushowania na `main` bezpośrednio; commity po polsku.
