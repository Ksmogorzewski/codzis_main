# codzis_main

PoC: portal partnera pod własną domeną. Partner loguje się swoim kluczem API, kupuje kredyty (mock bramka płatności) i publikuje ogłoszenia eventów (1 zdjęcie → S3). Każde ogłoszenie kosztuje kredyt. Eventy trafiają na kolejkę SQS, a worker na ECS je taguje i zapisuje do docelowej tabeli DynamoDB.

```
https://<domena>/        ──▶ CloudFront ──▶ S3 (strona, prywatny, OAC)
https://<domena>/api/*   ──▶ CloudFront ──▶ API GW (REST, API key, /{proxy+}) ──▶ Lambda ──▶ submissions + SQS
https://<domena>/photos/* ──▶ CloudFront ──▶ S3 (zdjęcia, prywatny; upload przez presigned POST)

importer ECS (EventBridge co 2 h): API UM Warszawy ──▶ schemat v1 ──▶ diff (S3) ──▶ SQS
SQS ──▶ tagger ECS (Fargate Spot): tagi DeepSeek ──▶ events (docelowa) + submissions.status = published
          ▲ RunTask
dispatcher (Lambda, EventBridge): co 5 min gdy ≥ 50 wiadomości; co 60 min gdy ≥ 1; zawsze max 1 task naraz
```

Portal (`index.html`): landing z cennikiem i logowaniem, po zalogowaniu zakładki Moje ogłoszenia / Dodaj nowe / Profil / Płatności. Mock bramka: `mock-pay.html`.

| Endpoint | Opis |
| --- | --- |
| `GET /api/me` | profil + saldo kredytów (pierwsze wywołanie zakłada partnera) |
| `GET /api/events` | zgłoszenia partnera ze statusem `queued` / `published` i tagami |
| `POST /api/events` | nowe ogłoszenie: transakcja odejmuje kredyt i zapisuje zgłoszenie, potem wiadomość na SQS; zwraca presigned POST na zdjęcie; `402` gdy brak kredytów, `503` (z kredytem zwróconym) gdy SQS nie przyjmie |
| `GET /api/payments` | historia płatności |
| `POST /api/payments` | `{"package": "standard"}` → płatność `pending` + `redirectUrl` do mock bramki |
| `GET /api/payments/{id}` | szczegóły płatności |
| `POST /api/payments/{id}/confirm` | mock "zapłacono": `paid` + dodanie kredytów (idempotentne, `409` przy powtórce) |
| `POST /api/payments/{id}/cancel` | anulowanie płatności `pending` |

Tabele DynamoDB: `events` (docelowa, pisze tylko worker), `submissions` i `payments` (GSI `byPartner`), `partners` (saldo). Pakiety, cena ogłoszenia i kredyty startowe: zmienne `credit_packages`, `event_cost_credits`, `starter_credits`.

## Struktura

- `run_task.py`, `tagger/` – tagowanie eventów przez AI (DeepSeek), jednorazowy task ECS: SQS → tagi → `events`. Szczegóły: [tagger/README.md](tagger/README.md)

- `infra/` – Terraform
- `src/api/handler.py` – Lambda API (walidacja pól: `TEXT_FIELDS`, `_event_input`)
- `src/dispatcher/handler.py` – Lambda uruchamiająca task taggera
- `src/importer/` – importer ECS: API UM Warszawy → wspólny schemat (`schema.py`, `sources.py`) → SQS
- `Dockerfile` (tagger), `src/importer/Dockerfile`, `scripts/push-images.sh` – obrazy ECS i ich build + push do ECR
- `src/web/` – portal (`index.html`, `app.js`), mock bramka (`mock-pay.*`), wspólne `common.js`, `styles.css`; `config.js` generuje Terraform

## Deploy

Wymaga hosted zone w Route53 dla domeny (lub delegowanej subdomeny).

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # uzupełnij domenę i partnerów
terraform init
terraform apply                                # pierwszy raz ~5-10 min (ACM + CloudFront)
terraform output -json partner_api_keys        # klucze do przekazania partnerom
aws ssm put-parameter --name "$(terraform output -raw um_api_token_parameter)" \
  --type SecureString --overwrite --value "<token dane.um.warszawa.pl>"
aws ssm put-parameter --name "$(terraform output -raw deepseek_api_key_parameter)" \
  --type SecureString --overwrite --value "sk-..."   # klucz DeepSeek (poza state'em)
cd ..
scripts/push-images.sh                         # obrazy taggera i importera (wymaga Dockera)
```

Do czasu wypchnięcia obrazu dispatcher będzie uruchamiał task, który nie wystartuje (brak obrazu w ECR), a wiadomości poczekają w kolejce (retencja 14 dni).

## Importer (API UM Warszawy → SQS)

Task ECS uruchamiany przez EventBridge (`importer_schedule`, domyślnie co 2 h; zbiory UM odświeżają się co 2 h). Zwykły Fargate, nie Spot: task trwa ~1 min.

| Źródło (`source`) | Endpoint (`POST`, nagłówek `Authorization: <token>`) | Mapowanie |
| --- | --- | --- |
| `um_kalendarz` | `get_bmm_kalendarz_wydarzen` | `kind=event`, terminy z `occurrence`; wydarzenia zakończone są pomijane |
| `um_sport` | `get_bmm_zajecia_sportowe` | `kind=recurring` (dni tygodnia + godzina startu → `schedule`) albo `event` gdy są konkretne daty; `dedicated` → `audience` |
| `um_boiska` | `get_be_otwarte_boiska` | `kind=venue`: jeden rekord na (szkoła, adres, typ obiektu), np. „Piłka nożna – SP 92”; godziny otwarcia z kilku wierszy scalone w `schedule` |

Przebieg dla każdego źródła: pobranie całego zbioru (API nie ma paginacji) → surowa kopia `s3://<data_bucket>/raw/<source>/…json.gz` (retencja `raw_snapshot_retention_days`) → mapowanie na schemat v1 → porównanie `contentHash` ze stanem `state/<source>.json` → **na SQS idą tylko nowe i zmienione rekordy** (JSON array po ≤ 20 rekordów) → zapis stanu. Pusta odpowiedź API nie nadpisuje stanu; awaria jednego źródła nie blokuje pozostałych (kod wyjścia 1).

Lokalny podgląd bez AWS: `UM_API_TOKEN=… AWS_REGION=eu-central-1 SQS_QUEUE_URL=- DATA_BUCKET=- python src/importer/main.py --dry-run`.

## Tagger AI (SQS → ECS → DynamoDB)

Kod: `run_task.py` + `tagger/` ([tagger/README.md](tagger/README.md)), obraz z `Dockerfile` w katalogu głównym.

- **Kontrakt wiadomości:** body = JSON array rekordów w schemacie v1 (`[{...}, ...]`). Importer wrzuca diffy, portal wrzuca `[rekord]` z `"source": "partner"`.
- **Na wiadomość:** `normalize` (rekordy ze `schemaVersion` przechodzą bez zmian; starsze surowe rekordy UM: id z `url`, offset `+01` → `+01:00`, `startsAt`/`endsAt` UTC, zdjęcia → `https`), pominięcie rekordów już istniejących w tabeli (przed wywołaniem modelu), tagowanie DeepSeek, zapis tylko otagowanych rekordów, `submissions.status = published` dla partnerów. Jeśli któryś rekord nie dostał tagów, wiadomość zostaje w kolejce i przy ponownym dostarczeniu tagowane są tylko brakujące.
- **Tagi** to wymiary z `tagger/prompt.py` (`theme`, `audience`, `format`, `cost`, `mode`), np. `{"theme": ["Teatr i performans"], "audience": "Dorośli (18-64)", ...}`.
- **Uruchamianie:** dispatcher odpala task na Fargate Spot (fallback: Fargate), task kończy się, gdy kolejka jest pusta. Kod wyjścia `1` = część wiadomości nie przeszła; po 5 próbach trafiają do `codzis-events-dlq`.
- **Klucz DeepSeek** jest w SSM (`terraform output deepseek_api_key_parameter`); z placeholderem `CHANGE_ME` task kończy się od razu, bez ruszania kolejki.
- Progi: `worker_min_messages` (50 wiadomości, nie rekordów), `worker_check_minutes` (5), `worker_max_wait_minutes` (60). Visibility timeout kolejki: 30 min (wywołania LLM).

## Rekord eventu: schemat v1 (tabela `events`)

Jeden kształt dla wszystkich źródeł (importer i portal partnera). Pełny opis pól: `src/importer/schema.py`.

| Pole | Opis |
| --- | --- |
| `id` | `kal-…` / `spt-…` / `bsk-…` = prefiks + `sha1(klucz źródła)[:12]`; partner: UUID |
| `source` | `um_kalendarz` \| `um_sport` \| `um_boiska` \| `partner` |
| `kind` | `event` (konkretne terminy) \| `recurring` (co tydzień) \| `venue` (obiekt otwarty w godzinach) |
| `title`, `lead`, `text`, `url` | `text` to HTML: sanityzować przy wyświetlaniu |
| `category`, `audience` | kategorie i grupy docelowe ze źródła (podpowiedzi dla taggera) |
| `district`, `online`, `venue {name, address}`, `location {lat, lon}` | `location` = `null` dla boisk i partnerów (brak współrzędnych w źródle) |
| `occurrences [{start, end, allDay}]` | ISO 8601 z offsetem; dla `kind=event` |
| `schedule [{day, start, end}]` | `monday`…`sunday`, `HH:MM`; dla `recurring` i `venue` |
| `startsAt`, `endsAt` | UTC, z `occurrences` (do sortowania/indeksów) |
| `imageUrl`, `attributes` | zdjęcie po https; dodatki specyficzne dla źródła (np. nawierzchnia boiska) |
| `contentHash`, `importedAt` | wykrywanie zmian w importerze |
| `tags` | dopisuje tagger (wymiary z `tagger/prompt.py`) |

Pola portalu partnera i ich walidacja: `TEXT_FIELDS` i `_event_input` w `src/api/handler.py`. Kategorie: zmienna `event_categories`, dzielnice: `local.warsaw_districts`.

## Ograniczenia PoC

- Klucz API to jedyny "login". Partner musi go chronić jak hasło, nie ma też resetu ani wygasania (poza usunięciem klucza).
- Klucze trafiają do state'u Terraforma (lokalnie, plaintext).
- Mock bramka: `confirm` woła sam partner, więc każdy zalogowany może dodać sobie kredyty. Przy prawdziwej bramce (np. Stripe, PayU, Przelewy24) zastąp to webhookiem od operatora, weryfikowanym podpisem.
- Kredyt jest pobierany przy zapisie ogłoszenia, przed uploadem zdjęcia. Jeśli upload się nie uda, `image.highlighted.path` wskazuje na nieistniejący plik.
- Czas z formularza jest interpretowany w strefie przeglądarki partnera.
- Ogłoszenie partnera pojawia się w tabeli `events` z opóźnieniem do `worker_max_wait_minutes` (przy małym ruchu).
- Brak alarmu na DLQ: zepsute wiadomości trzeba sprawdzać ręcznie.
- Tagger pomija rekordy, które już są w tabeli, więc **zmiany ze źródeł (nowy termin, opis) nie aktualizują tabeli docelowej**, mimo że importer je wysyła (do poprawy w taggerze: porównać `contentHash`).
- Rekordy usunięte w źródle zostają w tabeli (importer tylko loguje ich liczbę).
- API GW jest też dostępne bezpośrednio pod `execute-api` (z tym samym kluczem).
