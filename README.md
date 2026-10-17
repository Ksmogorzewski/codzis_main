# codzis_main

PoC: portal partnera pod własną domeną. Partner loguje się swoim kluczem API, kupuje kredyty (mock bramka płatności) i publikuje ogłoszenia eventów (1 zdjęcie → S3). Każde ogłoszenie kosztuje kredyt. Eventy trafiają na kolejkę SQS, a worker na ECS je taguje i zapisuje do docelowej tabeli DynamoDB.

```
https://<domena>/        ──▶ CloudFront ──▶ S3 (strona, prywatny, OAC)
https://<domena>/api/*   ──▶ CloudFront ──▶ API GW (REST, API key, /{proxy+}) ──▶ Lambda ──▶ submissions + SQS
https://<domena>/photos/* ──▶ CloudFront ──▶ S3 (zdjęcia, prywatny; upload przez presigned POST)

SQS ──▶ tagger ECS (Fargate Spot): normalizacja + tagi DeepSeek ──▶ events (docelowa) + submissions.status = published
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
- `Dockerfile`, `scripts/push-worker.sh` – obraz taggera i jego build + push do ECR
- `src/web/` – portal (`index.html`, `app.js`), mock bramka (`mock-pay.*`), wspólne `common.js`, `styles.css`; `config.js` generuje Terraform

## Deploy

Wymaga hosted zone w Route53 dla domeny (lub delegowanej subdomeny).

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # uzupełnij domenę i partnerów
terraform init
terraform apply                                # pierwszy raz ~5-10 min (ACM + CloudFront)
terraform output -json partner_api_keys        # klucze do przekazania partnerom
aws ssm put-parameter --name "$(terraform output -raw deepseek_api_key_parameter)" \
  --type SecureString --overwrite --value "sk-..."   # klucz DeepSeek (poza state'em)
cd ..
scripts/push-worker.sh                         # obraz taggera (wymaga Dockera)
```

Do czasu wypchnięcia obrazu dispatcher będzie uruchamiał task, który nie wystartuje (brak obrazu w ECR), a wiadomości poczekają w kolejce (retencja 14 dni).

## Tagger AI (SQS → ECS → DynamoDB)

Kod: `run_task.py` + `tagger/` ([tagger/README.md](tagger/README.md)), obraz z `Dockerfile` w katalogu głównym.

- **Kontrakt wiadomości:** body = JSON array rekordów w kształcie API UM Warszawy (`[{...}, ...]`). Backend importu wrzuca diffy, portal wrzuca `[rekord]` z `"source": "partner"` i własnym `id`.
- **Na wiadomość:** `normalize` (id = własne lub `sha1(url)[:12]`, `source` domyślnie `um_warszawa`, offset `+01` → `+01:00`, `startsAt`/`endsAt` UTC, zdjęcia → `https`), pominięcie rekordów już istniejących w tabeli (przed wywołaniem modelu), tagowanie DeepSeek, zapis tylko otagowanych rekordów, `submissions.status = published` dla partnerów. Jeśli któryś rekord nie dostał tagów, wiadomość zostaje w kolejce i przy ponownym dostarczeniu tagowane są tylko brakujące.
- **Tagi** to wymiary z `tagger/prompt.py` (`theme`, `audience`, `format`, `cost`, `mode`), np. `{"theme": ["Teatr i performans"], "audience": "Dorośli (18-64)", ...}`.
- **Uruchamianie:** dispatcher odpala task na Fargate Spot (fallback: Fargate), task kończy się, gdy kolejka jest pusta. Kod wyjścia `1` = część wiadomości nie przeszła; po 5 próbach trafiają do `codzis-events-dlq`.
- **Klucz DeepSeek** jest w SSM (`terraform output deepseek_api_key_parameter`); z placeholderem `CHANGE_ME` task kończy się od razu, bez ruszania kolejki.
- Progi: `worker_min_messages` (50 wiadomości, nie rekordów), `worker_check_minutes` (5), `worker_max_wait_minutes` (60). Visibility timeout kolejki: 30 min (wywołania LLM).

## Rekord eventu (tabela `events`)

Jedna tabela na eventy z obu źródeł. Rekord ma kształt eventu z API UM Warszawy (`title`, `lead`, `text`, `category`, `localization`, `address`, `map`, `occurrence`, `image`, `url`, `language`, `availableLanguages`), a na górnym poziomie nasze metadane:

| Pole | Opis |
| --- | --- |
| `id` | partner: UUID; UM Warszawa: deterministyczne z `url` (np. `um-<sha1(url)>`), żeby ponowny import nadpisywał rekord |
| `source` | `partner` \| `um_warszawa` |
| `partnerId`, `partnerName` | tylko `partner` (GSI `byPartner` jest przez to rzadki) |
| `startsAt`, `endsAt` | UTC, z `occurrence`: do sortowania/indeksów (DynamoDB nie indeksuje zagnieżdżonych pól) |
| `createdAt`, `updatedAt` | ISO, UTC |

Różnice w rekordach partnera: `category`/`localization` mają tylko `name` (bez `id` ze słownika UM), `map.features[].geometry` = `null` (brak geokodowania), `text` to HTML zbudowany z escapowanego tekstu. Pole `text` z obu źródeł trzeba sanityzować przy wyświetlaniu.

Pola formularza i ich walidacja: `TEXT_FIELDS` i `_event_input` w `src/api/handler.py`, formularz w `src/web/index.html`. Kategorie: zmienna `event_categories`, dzielnice: `local.warsaw_districts`.

## Ograniczenia PoC

- Klucz API to jedyny "login". Partner musi go chronić jak hasło, nie ma też resetu ani wygasania (poza usunięciem klucza).
- Klucze trafiają do state'u Terraforma (lokalnie, plaintext).
- Mock bramka: `confirm` woła sam partner, więc każdy zalogowany może dodać sobie kredyty. Przy prawdziwej bramce (np. Stripe, PayU, Przelewy24) zastąp to webhookiem od operatora, weryfikowanym podpisem.
- Kredyt jest pobierany przy zapisie ogłoszenia, przed uploadem zdjęcia. Jeśli upload się nie uda, `image.highlighted.path` wskazuje na nieistniejący plik.
- Czas z formularza jest interpretowany w strefie przeglądarki partnera.
- Ogłoszenie partnera pojawia się w tabeli `events` z opóźnieniem do `worker_max_wait_minutes` (przy małym ruchu).
- Brak alarmu na DLQ: zepsute wiadomości trzeba sprawdzać ręcznie.
- API GW jest też dostępne bezpośrednio pod `execute-api` (z tym samym kluczem).
