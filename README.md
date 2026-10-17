# codzis_main

PoC: portal partnera pod własną domeną. Partner loguje się swoim kluczem API, kupuje kredyty (mock bramka płatności) i publikuje ogłoszenia eventów (1 zdjęcie → S3). Każde ogłoszenie kosztuje kredyt. Eventy trafiają na kolejkę SQS, a worker na ECS je taguje i zapisuje do docelowej tabeli DynamoDB.

```
https://<domena>/        ──▶ CloudFront ──▶ S3 (strona, prywatny, OAC)
https://<domena>/api/*   ──▶ CloudFront ──▶ API GW (REST, API key, /{proxy+}) ──▶ Lambda ──▶ submissions + SQS
https://<domena>/photos/* ──▶ CloudFront ──▶ S3 (zdjęcia, prywatny; upload przez presigned POST)

importer ECS (EventBridge co 2 h): API UM Warszawy ──▶ schemat v1 ──▶ diff (S3) ──▶ SQS
SQS ──▶ tagger ECS (Fargate Spot): tagi DeepSeek ──▶ events (docelowa) + submissions.status = published
          ▲ RunTask
dispatcher (Lambda, EventBridge co 1 min): gdy w kolejce jest ≥ 1 wiadomość i tagger nie działa → RunTask
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

DNS domeny jest w home.pl, bez Route53. Portal działa pod `domain_name` (np. `waw-out.pl`) i `domain_aliases` (np. `www.waw-out.pl`). Rekordy w home.pl dodajesz ręcznie, dlatego deploy ma dwa etapy:

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # domena, aliasy, partnerzy
terraform init

# 1. certyfikat -> rekordy walidacyjne w home.pl (zostają na stałe: dzięki nim certyfikat sam się odnawia)
terraform apply -target=aws_acm_certificate.portal
terraform output acm_validation_records        # home.pl: CNAME <name> -> <value>, po jednym na domenę

# 2. reszta; apply czeka (do 2 h), aż certyfikat zostanie wydany (~5-30 min po dodaniu rekordów)
terraform apply
terraform output dns_records                   # home.pl: www -> CNAME <value>; domena główna -> ALIAS/ANAME <value>
```

**Zmiana domeny w działającym deployu:** zrób od razu pełny `terraform apply`, bez etapu 1. Przy `-target` Terraform próbuje usunąć stary certyfikat, który jest jeszcze podpięty pod CloudFront, i apply kończy się błędem. Gdy apply czeka na `aws_acm_certificate_validation`, w drugim terminalu uruchom `scripts/acm-records.sh`: pokaże rekordy do wpisania w home.pl. Domena musi już działać w DNS (świeżo zarejestrowana `.pl` potrzebuje na to od kilku minut do kilku godzin).

```sh
terraform output -json partner_api_keys        # klucze do przekazania partnerom
aws ssm put-parameter --name "$(terraform output -raw um_api_token_parameter)" \
  --type SecureString --overwrite --value "<token dane.um.warszawa.pl>"
aws ssm put-parameter --name "$(terraform output -raw deepseek_api_key_parameter)" \
  --type SecureString --overwrite --value "sk-..."   # klucz DeepSeek (poza state'em)
cd ..
scripts/push-images.sh                         # obrazy taggera i importera (wymaga Dockera)
```

Do czasu wypchnięcia obrazu dispatcher będzie uruchamiał task, który nie wystartuje (brak obrazu w ECR), a wiadomości poczekają w kolejce (retencja 14 dni).

## Initial load (pierwsze załadowanie danych)

Po `terraform apply`, ustawieniu obu sekretów w SSM i `scripts/push-images.sh`:

```sh
scripts/initial-load.sh
```

Skrypt:
1. sprawdza, czy sekrety nie mają wartości `CHANGE_ME`;
2. uruchamia importer od razu, bez czekania na harmonogram. W S3 nie ma jeszcze stanu, więc na kolejkę idzie wszystko: ok. 1220 rekordów w ~62 wiadomościach;
3. uruchamia tagger i powtarza to do opróżnienia kolejki (najwyżej 6 rund), bez czekania na dispatcher. Jeśli tagger już działa, bo uruchomił go dispatcher, skrypt czeka na niego zamiast startować drugi;
4. pokazuje stan kolejki i DLQ oraz liczbę rekordów w `events` według źródła.

Pojedyncze uruchomienia, także później: `scripts/run-task.sh importer|tagger` (czeka na koniec, kod wyjścia = kod kontenera, pokazuje logi taska). Podgląd na żywo: `aws logs tail /ecs/codzis-importer --follow` (tagger: `/ecs/codzis-worker`).

**Pełne przeładowanie** (np. po zmianie schematu albo mapowania):
1. Usuń stan importera: `aws s3 rm s3://$(terraform -chdir=infra output -raw data_bucket)/state/ --recursive`. Następny import wyśle wszystko od nowa.
2. Tagger pomija rekordy, które już są w `events`. Jeśli mają zostać otagowane ponownie, trzeba też wyczyścić tabelę, np. `terraform -chdir=infra apply -replace=aws_dynamodb_table.events`. To kasuje dane, a ogłoszenia partnerów wrócą do tabeli tylko po ponownym wysłaniu ich na kolejkę.

## Importer (API UM Warszawy → SQS)

Task ECS uruchamiany przez EventBridge (`importer_schedule`, domyślnie co 2 h; zbiory UM odświeżają się co 2 h). Zwykły Fargate, nie Spot: task trwa ~1 min.

| Źródło (`source`) | Endpoint (`POST`, nagłówek `Authorization: <token>`) | Mapowanie |
| --- | --- | --- |
| `um_kalendarz` | `get_bmm_kalendarz_wydarzen` | `kind=event`, terminy z `occurrence`; wydarzenia zakończone są pomijane |
| `um_sport` | `get_bmm_zajecia_sportowe` | `kind=recurring` (dni tygodnia + godzina startu → `schedule`) albo `event` gdy są konkretne daty; `dedicated` → `audience` |

Przebieg dla każdego źródła: pobranie całego zbioru (API nie ma paginacji) → surowa kopia `s3://<data_bucket>/raw/<source>/…json.gz` (retencja `raw_snapshot_retention_days`) → mapowanie na schemat v1 → porównanie `contentHash` ze stanem `state/<source>.json` → **na SQS idą tylko nowe i zmienione rekordy** (JSON array po ≤ 20 rekordów) → zapis stanu. Pusta odpowiedź API nie nadpisuje stanu; awaria jednego źródła nie blokuje pozostałych (kod wyjścia 1).

Lokalny podgląd bez AWS: `UM_API_TOKEN=… AWS_REGION=eu-central-1 SQS_QUEUE_URL=- DATA_BUCKET=- python src/importer/main.py --dry-run`.

## Tagger AI (SQS → ECS → DynamoDB)

Kod: `run_task.py` + `tagger/` ([tagger/README.md](tagger/README.md)), obraz z `Dockerfile` w katalogu głównym.

- **Kontrakt wiadomości:** body = JSON array rekordów w schemacie v1. Importer wrzuca diffy, portal wrzuca `[rekord]`.
- **Decyzja per rekord** (przed wywołaniem modelu, na podstawie rekordu w `events`):

  | Sytuacja | Co robi tagger |
  | --- | --- |
  | nowy rekord | taguje |
  | ten sam `contentHash` i `tagInputHash` | pomija |
  | zmienił się np. termin, a dane dla modelu bez zmian | zapisuje rekord ze starymi tagami, **bez LLM** |
  | zmienił się tytuł / opis / kategorie / grupy docelowe albo taksonomia | taguje ponownie |
  | rekord partnera (bez `contentHash`) już w tabeli | pomija (portal nie edytuje ogłoszeń) |

- **Model dostaje:** tytuł, lead, opis (bez HTML, przycięty do 1500 znaków), kategorie oraz podpowiedzi ze źródła: `audience_hint`, `kind`, `online`, `venue`.
- **Tagi** (`tags`, 10 wymiarów z `tagger/prompt.py`): `theme`, `audience` (do 3), `format`, `cost`, `mode`, `setting` (w pomieszczeniu / na zewnątrz), `registration` (wstęp wolny / zapisy / bilet), `activity_level`, `occasion` (z dziećmi, na randkę…), `accessibility`. Zmiana taksonomii zmienia `taxonomyVersion`, więc rekordy, które przyjdą ponownie, zostaną przetagowane.
- **Parametry z danych** (`facets`, bez LLM): `timeOfDay`, `days`, `weekend`, `multiDay`, `recurring`.
- **TTL:** `expiresAt` = koniec eventu + 1 dzień; DynamoDB sam usuwa zakończone eventy. Zajęcia cykliczne nie wygasają.
- **Koszt:** każda wiadomość loguje tokeny i przybliżony koszt (`LLM: … ~$…`) w `/ecs/codzis-worker`.
- **Uruchamianie:** dispatcher odpala task na Fargate Spot (fallback: Fargate), task kończy się, gdy kolejka jest pusta. Kod wyjścia `1` = część wiadomości nie przeszła; po 5 próbach trafiają do `codzis-events-dlq`.
- **Klucz DeepSeek** jest w SSM (`terraform output deepseek_api_key_parameter`); z placeholderem `CHANGE_ME` task kończy się od razu, bez ruszania kolejki.
- **Start taggera:** dispatcher co minutę (`worker_check_minutes`) sprawdza kolejkę i uruchamia tagger, gdy jest w niej co najmniej `worker_min_messages` wiadomości (domyślnie 1, czyli przy każdej). Od pojawienia się wiadomości do startu kontenera mijają ~1-2 min. Visibility timeout kolejki: 30 min.

## Rekord eventu: schemat v1 (tabela `events`)

Jeden kształt dla wszystkich źródeł (importer i portal partnera). Pełny opis pól: `src/importer/schema.py`.

| Pole | Opis |
| --- | --- |
| `id` | `kal-…` / `spt-…` = prefiks + `sha1(klucz źródła)[:12]`; partner: UUID |
| `origin` | **skąd pochodzi event:** `um_warszawa` (otwarte dane UM, importer) \| `partner` (portal partnera) |
| `source` | szczegółowe źródło: `um_kalendarz` \| `um_sport` \| `partner` |
| `kind` | `event` (konkretne terminy) \| `recurring` (zajęcia co tydzień) |
| `title`, `lead`, `text`, `url` | `text` to HTML: sanityzować przy wyświetlaniu |
| `category`, `audience` | kategorie i grupy docelowe ze źródła (podpowiedzi dla taggera) |
| `district`, `online`, `venue {name, address}`, `location {lat, lon}` | `location` = `null` dla partnerów i części eventów UM (brak współrzędnych w źródle) |
| `occurrences [{start, end, allDay}]` | ISO 8601 z offsetem; dla `kind=event` |
| `schedule [{day, start, end}]` | `monday`…`sunday`, `HH:MM`; dla `recurring` |
| `startsAt`, `endsAt` | UTC, z `occurrences` (do sortowania/indeksów) |
| `imageUrl`, `attributes` | zdjęcie po https; dodatki specyficzne dla źródła |
| `contentHash`, `importedAt` | wykrywanie zmian w importerze |
| `tags` | dopisuje tagger: 10 wymiarów z `tagger/prompt.py` |
| `facets` | dopisuje tagger, z danych: `timeOfDay`, `days`, `weekend`, `multiDay`, `recurring` |
| `tagInputHash`, `taxonomyVersion`, `expiresAt` | tagger: wykrywanie zmian dla modelu, wersja taksonomii, TTL (epoch) |

Pola portalu partnera i ich walidacja: `TEXT_FIELDS` i `_event_input` w `src/api/handler.py`. Kategorie: zmienna `event_categories`, dzielnice: `local.warsaw_districts`.

## Ograniczenia PoC

- Klucz API to jedyny "login". Partner musi go chronić jak hasło, nie ma też resetu ani wygasania (poza usunięciem klucza).
- Klucze trafiają do state'u Terraforma (lokalnie, plaintext).
- Mock bramka: `confirm` woła sam partner, więc każdy zalogowany może dodać sobie kredyty. Przy prawdziwej bramce (np. Stripe, PayU, Przelewy24) zastąp to webhookiem od operatora, weryfikowanym podpisem.
- Kredyt jest pobierany przy zapisie ogłoszenia, przed uploadem zdjęcia. Jeśli upload się nie uda, `image.highlighted.path` wskazuje na nieistniejący plik.
- Czas z formularza jest interpretowany w strefie przeglądarki partnera.
- **Domena główna bez `www`:** CNAME na apexie jest niedozwolony, a CloudFront nie ma stałego IP. `waw-out.pl` zadziała tylko, jeśli home.pl obsługuje rekord ALIAS/ANAME. Jeśli nie, ustaw `domain_name = "www.waw-out.pl"` i w home.pl przekieruj `waw-out.pl` na `https://www.waw-out.pl`.
- Ogłoszenie partnera pojawia się w tabeli `events` po ~2-5 min (start kontenera + tagowanie).
- Brak alarmu na DLQ: zepsute wiadomości trzeba sprawdzać ręcznie.
- Rekordy usunięte w źródle przed końcem (np. odwołane eventy) zostają w tabeli do `expiresAt`; zajęcia cykliczne usunięte w źródle zostają na stałe (importer tylko loguje ich liczbę).
- Zmiana taksonomii przetaguje tylko rekordy, które przyjdą ponownie; żeby przetagować wszystko: pełne przeładowanie (sekcja Initial load).
- API GW jest też dostępne bezpośrednio pod `execute-api` (z tym samym kluczem).
