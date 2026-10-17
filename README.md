# codzis_main

PoC **WarsawNow**: co robić w Warszawie dziś.
- **Portal klienta** (`portal.waw-out.pl`): logowanie e-mailem lub Google (Cognito), profil zbierany kafelkami (onboarding) i zapisywany w DynamoDB, a na jego podstawie zakładka **Rekomendacje** (RAG: embeddingi eventów + ranking DeepSeek z uzasadnieniem „Pasuje: …”).
- **Panel organizatora** (`partner.waw-out.pl`): partner loguje się kluczem API, kupuje kredyty (mock bramka płatności) i publikuje ogłoszenia (1 zdjęcie → S3, 1 ogłoszenie = 1 kredyt).
- **Dane:** ogłoszenia partnerów i eventy z otwartych danych UM trafiają na kolejkę SQS, a tagger AI na ECS taguje je i zapisuje do docelowej tabeli DynamoDB.

Frontend obu stron to React + TypeScript (`src/frontend`, Vite), wygląd według makiet z „UI mockups request”.

```
https://portal.<domena>/ ──▶ CloudFront ──▶ S3 (portal klienta, React)
     logowanie: Cognito (e-mail + hasło: API Cognito; Google: Hosted UI + PKCE)
     API: HTTP API (JWT authorizer Cognito) ──▶ Lambda client-api ──▶ users (profil + preferencje)
          GET /api/recommendations ──▶ Lambda recommender (obraz kontenera: model + indeks z S3) ──▶ DeepSeek

https://<domena>/        ──▶ CloudFront ──▶ S3 (panel organizatora, React, prywatny, OAC)
https://<domena>/api/*   ──▶ CloudFront ──▶ API GW (REST, API key, /{proxy+}) ──▶ Lambda ──▶ submissions + SQS
https://<domena>/photos/* ──▶ CloudFront ──▶ S3 (zdjęcia, prywatny; upload przez presigned POST)

importer ECS (EventBridge co 2 h): API UM Warszawy ──▶ schemat v1 ──▶ diff (S3) ──▶ SQS
SQS ──▶ tagger ECS (Fargate Spot): tagi DeepSeek ──▶ events (docelowa) + submissions.status = published
          ▲ RunTask
dispatcher (Lambda, EventBridge co 1 min): gdy w kolejce jest ≥ 1 wiadomość i tagger nie działa → RunTask
recommender (EventBridge co 30 min): events ──▶ embeddingi nowych eventów ──▶ S3 recommender/index.npz
```

Panel organizatora: logowanie kluczem API, potem Moje wydarzenia (statusy, tagi AI), Dodaj wydarzenie (formularz z podglądem karty) i Płatności i kredyty. Mock bramka: `mock-pay.html`.

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
- `src/client_api/` – Lambda API portalu klienta: `handler.py` (profil), `onboarding.py` (pytania + mapowanie odpowiedzi na preferencje)
- `recommender/` – silnik rekomendacji (RAG): embeddingi, filtry, ranking, DeepSeek. Szczegóły: [recommender/README.md](recommender/README.md)
- `src/recommender_api/` – Lambda z obrazu kontenera: `GET /api/recommendations` + budowa indeksu (`Dockerfile`, build z katalogu głównego)
- `src/frontend/` – React + TS (Vite): `client/` portal klienta, `partner/` panel organizatora (+ `mock-pay.html`), `shared/`; `config.js` generuje Terraform

## Deploy

Frontend trzeba zbudować przed `terraform apply`, bo Terraform wgrywa na S3 pliki z `src/frontend/dist`. Bez builda plan zatrzyma się z błędem (`terraform_data.frontend_build`), zamiast skasować strony:

```sh
scripts/build-frontend.sh        # npm ci + testy + build obu aplikacji
```

DNS domeny jest w home.pl, bez Route53. Portal działa pod `domain_name` (`partner.waw-out.pl`); opcjonalne dodatkowe nazwy na tym samym certyfikacie: `domain_aliases` (domyślnie brak). Rekordy w home.pl dodajesz ręcznie, dlatego deploy ma dwa etapy:

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # domena, aliasy, partnerzy
terraform init

# 1. certyfikat -> rekordy walidacyjne w home.pl (zostają na stałe: dzięki nim certyfikat sam się odnawia)
terraform apply -target=aws_acm_certificate.portal
terraform output acm_validation_records        # home.pl: CNAME <name> -> <value>, po jednym na domenę

# 2. reszta; apply czeka (do 2 h), aż certyfikat zostanie wydany (~5-30 min po dodaniu rekordów)
terraform apply
terraform output dns_records                   # home.pl: CNAME, Host "partner" -> <value> (dXXXX.cloudfront.net.)
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

## Portal klienta (WarsawNow)

**Domena:** `client_domain_name` (domyślnie `portal.waw-out.pl`). W home.pl potrzebne są 2 rekordy CNAME:
- walidacja certyfikatu z `terraform output client_acm_validation_records` (albo `scripts/acm-records.sh portal.waw-out.pl` w trakcie apply);
- `portal` → CloudFront z `terraform output client_dns_records`.

W polu Host wpisujesz część przed `.waw-out.pl`.

**Logowanie (Cognito):**
- **E-mail + hasło:** własny formularz strony; rejestracja z 6-cyfrowym kodem z e-maila i reset hasła. Domyślna wysyłka Cognito ma limit ~50 e-maili dziennie.
- **Google (domyślnie wyłączone):** bez `google_client_id` nie powstaje ani dostawca Google, ani domena Hosted UI, a strona nie pokazuje przycisku. Żeby włączyć, w [Google Cloud Console](https://console.cloud.google.com/apis/credentials) utwórz *OAuth client ID → Web application*:
  - Authorized JavaScript origins: `terraform output cognito_hosted_ui`;
  - Authorized redirect URIs: `terraform output google_oauth_redirect_uri`.

  Client ID i secret wpisz do `infra/terraform.tfvars` (`google_client_id`, `google_client_secret`) i zrób `terraform apply`; przycisk „Kontynuuj przez Google” pojawi się sam. Ekran zgody w trybie *Testing* wpuszcza tylko dodanych testerów.
- **E-maile** (kod przy rejestracji, kod resetu hasła) wysyła Cognito z domyślnej skrzynki AWS (`no-reply@verificationemail.com`, temat i treść z `verification_message_template` w `infra/client_auth.tf`). Limit to ~50 e-maili dziennie na konto AWS i nie da się zmienić nadawcy. Docelowo: Amazon SES z domeną `waw-out.pl` (rekordy DKIM w home.pl + wyjście z trybu sandbox), potem w Cognito `email_sending_account = "DEVELOPER"`.
- Sesja jest trzymana w `localStorage` (refresh token na 30 dni). Konto e-mail i konto Google z tym samym adresem to w Cognito dwa osobne konta.

**API** (HTTP API, ID token Cognito w `Authorization: Bearer …`, weryfikuje go API Gateway):

| Endpoint | Opis |
| --- | --- |
| `GET /api/me` | profil (pierwsze wywołanie zakłada rekord), `needsOnboarding`, `onboardingOutdated` |
| `GET /api/onboarding` | kafelki z pytaniami (ikony, limity wyborów, wymagane pola) |
| `PUT /api/profile` | `{"answers": {"who": ["kids"], ...}}` → walidacja, preferencje, zapis |
| `GET /api/recommendations` | `?when=today\|tomorrow\|weekend\|week\|date&date=2026-10-30&q=jazz&limit=16` → karty wydarzeń z uzasadnieniem (sekcja Rekomendacje); `202 {"status": "preparing"}` gdy zestaw właśnie się liczy, `409` bez profilu, `503` zanim powstanie indeks |

**Onboarding:** pytania i mapowanie odpowiedzi są w jednym miejscu, `src/client_api/onboarding.py`; frontend tylko je wyświetla. Jest 10 kafelków:
- wymagane: z kim, klimat (maks. 2), co odkryć (maks. 2), gdzie (dzielnica i zasięg);
- opcjonalne: sprawy miejskie, kiedy, budżet, styl (pod dachem / plener, aktywność), formuła (na żywo / online, zapisy), o Tobie (wiek, dostępność).

**Rekord użytkownika (tabela `codzis-users`, klucz `userId` = `sub` z Cognito, PITR włączone):**

| Pole | Opis |
| --- | --- |
| `email`, `displayName`, `picture`, `identityProvider` | z tokenu (`Google` / `Cognito`) |
| `onboarding` | `{version, completedAt, answers}`: surowe odpowiedzi; zmiana pytań zmienia `version` |
| `preferences` | odpowiedzi przemapowane na słownik eventów: `themes`, `formats`, `audience`, `occasion`, `activityLevel`, `cost`, `mode`, `setting`, `registration`, `accessibility` (opcje taksonomii taggera), `interests` (kategorie kalendarza UM), `days`/`timeOfDay`/`weekend` (jak `facets` eventów), `district`, `travelRange`, `maxPrice`, `ageRange` |
| `ragProfile` | tekst pod RAG, np. `interests=[Czas wolny, Kultura] \| district=Śródmieście \| cost=Bezpłatne \| mode=Stacjonarne \| audience=Dorośli (18-64) \| …` |

**Lokalny development** na wdrożonej infrze:
- `scripts/frontend-dev.sh client` (http://localhost:8000; adres jest w callbackach Cognito i w CORS API);
- `scripts/frontend-dev.sh partner` (http://localhost:8001; `/api` idzie przez proxy do domeny panelu).

Testy frontendu: `npm --prefix src/frontend test`.

## Rekomendacje (RAG)

Zakładka **Rekomendacje** w portalu klienta: wybór dnia (dziś / jutro / weekend / 7 dni / inny dzień do 60 dni naprzód), wyszukiwanie tekstem („jazz”, „joga”), kategorie i karty jak w makiecie (cena, miejsce, termin, „Pasuje: …”, Trasa, Bilet / Szczegóły). Silnik to pakiet [`recommender/`](recommender) z brancha `llm`, dostosowany do schematu v1 eventów.

**Zapisane zestawy (tabela `codzis-recommendations`):** rekomendacje liczą się raz i są zapisywane per użytkownik (`userId` + okno, daty i fraza). Ponowne wejście, przełączanie dni i odświeżanie strony czytają zapis.
- **Z góry** liczą się zestawy na dziś, jutro i najbliższy weekend:
  - w nocy dla osób aktywnych w ostatnich 14 dniach (`recommender_precompute_schedule`, domyślnie 3:00 UTC);
  - od razu po zmianie preferencji (client-api wywołuje rekomender asynchronicznie);
  - przy logowaniu, jeśli któregoś brakuje.
- **Na żądanie** liczy się inny dzień i wyszukiwanie frazą, potem też z zapisu.
- **Odświeżanie:** zestaw starszy niż 12 h (`recommender_results_max_age_hours`, żeby złapać nowe eventy) albo z małą liczbą trwających jeszcze wydarzeń pokazuje się od razu i jednocześnie liczy się od nowa w tle (`"updating": true`). Zakończone wydarzenia znikają z kart same. Czekać trzeba tylko wtedy, gdy zestawu jeszcze nie ma albo zmienił się profil (`202 preparing`, strona dopytuje co 2 s).
- **Liczenie zawsze w tle** (GET zleca je asynchronicznie tej samej Lambdzie, więc nie ogranicza go limit 30 s HTTP API), w dwóch fazach: najpierw filtry + wektory (sekundy, zestaw od razu do zapisu), potem DeepSeek (do 60 s, dla dziś / jutro / weekend równolegle). Strona sama podmienia listę, gdy wersja z AI jest gotowa.
- **Bez dublowania:** liczony zestaw dostaje claim w tabeli, więc drugi chętny czeka, zamiast liczyć to samo; claim wygasa po 3 min, gdyby liczenie padło. Strona po pierwszym zestawie dociąga w tle pozostałe z dziś / jutro / weekend.

**Jak dobieramy propozycje** (`src/recommender_api/user_context.py` mapuje `preferences` z onboardingu):
1. **Twarde filtry:** termin w wybranym oknie (już zakończone odpadają; zajęcia cykliczne wg dni tygodnia), dzielnica wg zasięgu dojazdu (okolica / sąsiednie dzielnice / cała Warszawa), koszt („tylko bezpłatne”), forma (na żywo / online), grupa odbiorców, budżet.
2. **Podobieństwo wektorowe:** model `paraphrase-multilingual-MiniLM-L12-v2` (lokalnie, CPU) porównuje profil (tematy, formaty, kategorie) albo wpisaną frazę z tekstem eventu (tytuł, kategorie, tagi AI, opis).
3. **Miękkie preferencje:** drobne punkty za zgodność tagów (tematy, formaty, z kim, aktywność, plener / pod dachem, zapisy, dostępność), porę dnia, bliskość dzielnicy; mniej za „wydarzenia” trwające miesiącami (to zwykle programy, nie propozycja na dziś). Potem dedupe tytułów i różnorodność (nie 5 kart z jednej pływalni).
4. **DeepSeek** (opcjonalnie, ten sam klucz co tagger): układa najlepszych kandydatów (tylu, ile kart prosi strona: 16) i pisze uzasadnienia. Przy błędzie lub po 60 s zostaje kolejność wektorowa z uzasadnieniem z reguł.

Gdy w okolicy wyjdą mniej niż 4 propozycje, obszar poszerza się sam (strona to pokazuje).

**Indeks:** `s3://<data_bucket>/recommender/index.npz` (wektory + odchudzone eventy). EventBridge co 30 min (`recommender_refresh_minutes`) skanuje tabelę `events` i liczy embeddingi tylko dla nowych lub zmienionych tekstów. Nowe eventy trafiają do zapisanych zestawów przy ich kolejnym przeliczeniu (najpóźniej po 12 h). Drugi harmonogram co 5 min trzyma model w pamięci (`recommender_keep_warm`), bo zimny start z torchem trwa kilkanaście sekund. Koszt: grosze miesięcznie (Lambda płatna za czas wywołań, ECR ~0,25 USD/mies. za obraz 2,3 GB).

**Wdrożenie** (Lambda potrzebuje istniejącego obrazu, więc za pierwszym razem dwa applye):
```sh
terraform -chdir=infra apply -target=aws_ecr_repository.recommender
scripts/push-images.sh recommender    # build arm64 (torch CPU + model w obrazie), push do ECR
scripts/build-frontend.sh
terraform -chdir=infra apply          # Lambda, trasa w HTTP API, harmonogramy, nowy frontend
scripts/recommender-refresh.sh        # pierwszy indeks od razu (~1-3 min), zamiast czekać 30 min
```
Kolejne zmiany kodu rekomendera: `scripts/push-images.sh recommender` (sam podmienia kod Lambdy). Nowe eventy trafiają do rekomendacji przy najbliższym odświeżeniu indeksu, a od razu po `scripts/recommender-refresh.sh`.

**Lokalnie, bez AWS** (zrzut tabeli `events` do JSON-a):
```sh
docker build --platform linux/arm64 --provenance=false -f src/recommender_api/Dockerfile -t codzis-recommender .
docker run --rm -v "$PWD/tmp:/data" -e EVENTS_FILE=/data/events.json -e INDEX_PATH=/data/index.npz \
  -e AWS_DEFAULT_REGION=eu-central-1 --entrypoint python codzis-recommender \
  -c 'import handler; print(handler.handler({"action": "refresh"}, None))'
```
Z `INDEX_PATH` i `EVENTS_FILE` handler zapisuje indeks do pliku zamiast do S3 i czyta eventy z pliku zamiast z DynamoDB.

Strojenie: wagi miękkich preferencji w `recommender/retriever/scoring.py` (`BOOSTS`), sąsiedztwo dzielnic w `src/recommender_api/user_context.py`, prompt rankingu w `recommender/ranker.py`, wyłączenie LLM: `recommender_llm_enabled = false`.

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

> **Blokada:** `dane.um.warszawa.pl` odrzuca połączenia z adresów IP AWS (timeout już na TCP; z polskiego łącza API odpowiada w 1-3 s, a z VPC działają SQS, DeepSeek i `um.warszawa.pl`). Do czasu rozwiązania harmonogram w ECS jest wyłączony (`importer_schedule_enabled = false`), a import uruchamia się lokalnie: `scripts/import-local.sh` (Docker + twoje credentiale AWS, zapis do S3/SQS jak w ECS). Możliwe rozwiązania docelowe: whitelista stałego IP po stronie UM (wymaga NAT z Elastic IP) albo uruchamianie importera z hosta w Polsce.

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
| `declared` | tylko partner: koszt, wejście, miejsce, dla kogo, dostępność podane w formularzu; tagger przepisuje je do `tags` zamiast zgadywać |
| `tags` | dopisuje tagger: 10 wymiarów z `tagger/prompt.py` |
| `facets` | dopisuje tagger, z danych: `timeOfDay`, `days`, `weekend`, `multiDay`, `recurring` |
| `tagInputHash`, `taxonomyVersion`, `expiresAt` | tagger: wykrywanie zmian dla modelu, wersja taksonomii, TTL (epoch) |

Pola portalu partnera i ich walidacja: `TEXT_FIELDS`, `DECLARED_FIELDS` i `_event_input` w `src/api/handler.py`. Opcje w `DECLARED_FIELDS` muszą być dokładnie opcjami z `tagger/prompt.py` (wartość spoza taksonomii tagger pominie); portal pobiera je z `GET /api/me` (`formOptions`). Cena (`priceMin`/`priceMax`, tylko przy „Płatne”) i link do biletów lądują w `attributes`. Kategorie: zmienna `event_categories`, dzielnice: `local.warsaw_districts`.

## Wydarzenia demo (prezentacja)

`src/importer/demo_events.json`: 31 dopracowanych, w pełni otagowanych wydarzeń pod prezentację (koncerty, warsztaty, sport, rodziny, seniorzy, sprawy miejskie, jedno online), ze zdjęciami z Unsplash. Organizatorzy i lokale są fikcyjne (przy prawdziwych ulicach), plenerowe dzieją się w przestrzeni publicznej (bulwary, parki, place). Terminy liczone są względem początku prezentacji, więc zawsze jest coś na dziś, jutro i weekend.

```sh
scripts/demo-events.sh --dry-run                    # podgląd rekordów
scripts/demo-events.sh --start 2026-10-20T14:00     # wysyłka (czas warszawski; bez --start: teraz)
scripts/demo-events.sh --delete                     # po prezentacji
```

Wysyłka idzie zwykłą drogą: SQS → tagger (dispatcher odpala go w ciągu minuty, tagowanie ~2-4 min) → `codzis-events`. Skrypt czeka na zapis, przebudowuje indeks rekomendera i usuwa zapisane zestawy rekomendacji, żeby przy najbliższym wejściu policzyły się już z wydarzeniami demo. Wszystkie wymiary tagów są zadeklarowane wprost (`declared`, jak u partnerów), więc tagger zostawia dokładnie te wartości.

W UI wydarzenia demo nie są oznaczone; w polu „Źródło” stoi fikcyjny organizator. W danych rozpoznasz je po `origin` = `source` = `"demo"` i id `demo-…`. Zakończone usuwa TTL, wystawy wielodniowe zostają do miesiąca, więc po prezentacji uruchom `--delete`. Zmiana danych: edytuj JSON (tagi tylko z `tagger/prompt.py`, `image` = id zdjęcia z Unsplash) i wyślij ponownie; tagger zaktualizuje rekordy o tych samych `key`.

## Ograniczenia PoC

- Klucz API to jedyny "login". Partner musi go chronić jak hasło, nie ma też resetu ani wygasania (poza usunięciem klucza).
- Klucze trafiają do state'u Terraforma (lokalnie, plaintext).
- Mock bramka: `confirm` woła sam partner, więc każdy zalogowany może dodać sobie kredyty. Przy prawdziwej bramce (np. Stripe, PayU, Przelewy24) zastąp to webhookiem od operatora, weryfikowanym podpisem.
- Kredyt jest pobierany przy zapisie ogłoszenia, przed uploadem zdjęcia. Jeśli upload się nie uda, `image.highlighted.path` wskazuje na nieistniejący plik.
- Czas z formularza jest interpretowany w strefie przeglądarki partnera.
- **Domena główna bez subdomeny** (np. samo `waw-out.pl`) nie zadziała z CloudFront przez home.pl: CNAME wymaga hosta, a rekord A wymagałby stałego IP, którego CloudFront nie ma. Dlatego obie strony są na subdomenach (`partner.`, `portal.`).
- Rekomendacje: nowy event trafia do indeksu w ciągu 30 min, a do zapisanych zestawów przy ich przeliczeniu (najpóźniej po 12 h); sąsiedztwo dzielnic jest przybliżone; brak jeszcze sygnałów zwrotnych (polubienia → `liked_event_ids`), które recommender już obsługuje.
- Nocne przeliczenie to jedno wywołanie Lambdy (do 15 min, ~15-25 s na osobę z LLM): wystarczy na kilkadziesiąt aktywnych osób, przy większej skali trzeba je rozłożyć (np. SQS).
- Pierwsze zapytanie po zimnym starcie Lambdy rekomendera trwa kilkanaście sekund (strona pokazuje komunikat i raz ponawia); harmonogram „warmup” zwykle temu zapobiega.
- Ogłoszenie partnera pojawia się w tabeli `events` po ~2-5 min (start kontenera + tagowanie).
- Brak alarmu na DLQ: zepsute wiadomości trzeba sprawdzać ręcznie.
- Rekordy usunięte w źródle przed końcem (np. odwołane eventy) zostają w tabeli do `expiresAt`; zajęcia cykliczne usunięte w źródle zostają na stałe (importer tylko loguje ich liczbę).
- Zmiana taksonomii przetaguje tylko rekordy, które przyjdą ponownie; żeby przetagować wszystko: pełne przeładowanie (sekcja Initial load).
- API GW jest też dostępne bezpośrednio pod `execute-api` (z tym samym kluczem).
