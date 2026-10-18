# WarsawNow – dokumentacja techniczna

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
https://<domena>/api/*   ──▶ CloudFront ──▶ API GW (REST, token Google z Cognito albo API key, /{proxy+}) ──▶ Lambda ──▶ submissions + SQS
https://<domena>/photos/* ──▶ CloudFront ──▶ S3 (zdjęcia, prywatny; upload przez presigned POST)

importer ECS (EventBridge co 2 h): API UM Warszawy ──▶ schemat v1 ──▶ diff (S3) ──▶ SQS
SQS ──▶ tagger ECS (Fargate Spot): tagi DeepSeek ──▶ events (docelowa) + submissions.status = published
          ▲ RunTask
dispatcher (Lambda, EventBridge co 1 min): gdy w kolejce jest ≥ 1 wiadomość i tagger nie działa → RunTask
recommender (EventBridge co 30 min): events ──▶ embeddingi nowych eventów ──▶ S3 recommender/index.npz
```

Panel organizatora: logowanie przez Google (pierwsze logowanie zakłada konto organizatora) albo, bez skonfigurowanego Google, kluczem API; potem Moje wydarzenia (statusy, tagi AI), Dodaj wydarzenie (formularz z podglądem karty) i Płatności i kredyty. Mock bramka: `mock-pay.html`.

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

- `run_task.py`, `tagger/` – tagowanie eventów przez AI (DeepSeek), jednorazowy task ECS: SQS → tagi → `events`; przy zapisie zdjęcie w standardzie (`tagger/images.py`). Szczegóły: [tagger/README.md](../tagger/README.md)

- `infra/` – Terraform
- `src/api/` – Lambda API panelu partnera: `handler.py` (routing), `events.py` (ogłoszenia, walidacja pól: `TEXT_FIELDS`, `_event_input`), `payments.py` (płatności), `store.py` (AWS, kredyty), `config.py` (zmienne środowiskowe)
- `src/layers/common/` – warstwa Lambda `codzis_common` (wspólne helpery HTTP dla `src/api` i `src/client_api`)
- `src/dispatcher/handler.py` – Lambda uruchamiająca task taggera
- `src/importer/` – importer ECS: API UM Warszawy → wspólny schemat (`schema.py`, `sources.py`) → SQS
- `Dockerfile` (tagger), `src/importer/Dockerfile`, `scripts/push-images.sh` – obrazy ECS i ich build + push do ECR
- `src/client_api/` – Lambda API portalu klienta: `handler.py` (profil), `onboarding.py` (pytania + mapowanie odpowiedzi na preferencje)
- `recommender/` – silnik rekomendacji (RAG): embeddingi, filtry, ranking, DeepSeek. Szczegóły: [recommender/README.md](../recommender/README.md)
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
# terraform.tfvars (domena, aliasy, partnerzy) jest w repo - edytuj go zamiast kopiować .example
../scripts/bootstrap-tfstate.sh                # jednorazowo: bucket S3 na state (lock: .tflock w buckecie)
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
terraform output -json partner_api_keys        # klucze do przekazania partnerom (tylko bez logowania Google)
aws ssm put-parameter --name "$(terraform output -raw um_api_token_parameter)" \
  --type SecureString --overwrite --value "<token dane.um.warszawa.pl>"
aws ssm put-parameter --name "$(terraform output -raw deepseek_api_key_parameter)" \
  --type SecureString --overwrite --value "sk-..."   # klucz DeepSeek (poza state'em)
cd ..
scripts/push-images.sh                         # obrazy taggera i importera (wymaga Dockera)
scripts/resize-images.sh                       # zdjęcia wydarzeń już w tabeli do standardu (jednorazowo, Docker)
```

Do czasu wypchnięcia obrazu dispatcher będzie uruchamiał task, który nie wystartuje (brak obrazu w ECR), a wiadomości poczekają w kolejce (retencja 14 dni).

## Portal klienta (WarsawNow)

**Domena:** `client_domain_name` (domyślnie `portal.waw-out.pl`). W home.pl potrzebne są 2 rekordy CNAME:
- walidacja certyfikatu z `terraform output client_acm_validation_records` (albo `scripts/acm-records.sh portal.waw-out.pl` w trakcie apply);
- `portal` → CloudFront z `terraform output client_dns_records`.

W polu Host wpisujesz część przed `.waw-out.pl`.

**Logowanie (Cognito):**
- **E-mail + hasło:** własny formularz strony; rejestracja z 6-cyfrowym kodem z e-maila i reset hasła. Domyślna wysyłka Cognito ma limit ~50 e-maili dziennie.
- **Google (domyślnie wyłączone):** jeden klient OAuth Google dla portalu klienta i panelu organizatora. Bez sekretu `codzis/google-oauth` w AWS Secrets Manager nie powstają dostawcy Google ani domeny Hosted UI, portal nie pokazuje przycisku, a panel loguje kluczem API. Żeby włączyć, w [Google Cloud Console](https://console.cloud.google.com/auth/overview):
  1. *Google Auth Platform*: nazwa aplikacji i e-mail pomocy, odbiorcy *External*. W *Branding*: strona główna `https://portal.waw-out.pl/`, polityka prywatności `https://portal.waw-out.pl/polityka-prywatnosci.html` (`src/frontend/client/public/polityka-prywatnosci.html`), *Authorized domains* `amazoncognito.com` i `waw-out.pl`. Potem *Audience → Publish app* (w trybie *Testing* wejdą tylko dodani testerzy, do 100). Zakresy `openid`, `email`, `profile` nie wymagają weryfikacji przez Google.
  2. *Clients → Create client → Web application*: *Authorized JavaScript origins* = `terraform output cognito_hosted_ui`, *Authorized redirect URIs* = `terraform output google_oauth_redirect_uris` (po dwa adresy: portal i panel).
  3. `terraform apply` zakłada w AWS Secrets Manager sekret `codzis/google-oauth` z wartością `CHANGE_ME` (ok. 0,40 USD miesięcznie). Wpisz w nim Client ID i secret jako JSON, poleceniem albo w konsoli AWS (Secrets Manager → `codzis/google-oauth` → *Retrieve secret value* → *Edit*). Terraform tej wartości potem nie rusza:
     ```sh
     aws secretsmanager put-secret-value --secret-id codzis/google-oauth \
       --secret-string '{"client_id":"….apps.googleusercontent.com","client_secret":"…"}'
     ```
     Potem `scripts/build-frontend.sh` i jeszcze raz `terraform apply`; `terraform output google_login_enabled` pokaże `true`. Przyciski „Kontynuuj z Google” (portal) i „Zaloguj się przez Google” (panel) pojawią się same.
- **Panel organizatora z Google:** osobna pula Cognito partnerów, tylko Google (`infra/partner_auth.tf`); REST API sprawdza ID token autoryzatorem Cognito w nagłówku `X-Id-Token` (`Authorization` CloudFront zdejmuje z GET-ów). Samoobsługa: pierwsze logowanie zakłada konto organizatora (`partnerId` = `sub`, kredyty startowe = `starter_credits`), ogłoszenia podpisuje imię i nazwisko z Google. Partnerzy z kluczem API (np. `demo`) w tym trybie nie mają dostępu; ich dane zostają pod starym `partnerId`.
- **E-maile** (kod przy rejestracji, kod resetu hasła) wysyła Cognito z domyślnej skrzynki AWS (`no-reply@verificationemail.com`, temat i treść z `verification_message_template` w `infra/client_auth.tf`). Limit to ~50 e-maili dziennie na konto AWS i nie da się zmienić nadawcy. Docelowo: Amazon SES z domeną `waw-out.pl` (rekordy DKIM w home.pl + wyjście z trybu sandbox), potem w Cognito `email_sending_account = "DEVELOPER"`.
- Sesja jest trzymana w `localStorage` (refresh token na 30 dni), w panelu organizatora w `sessionStorage` (do zamknięcia karty). Konto e-mail i konto Google z tym samym adresem to w Cognito dwa osobne konta. Imię klienta z Google to `given_name` (samo imię, jak pole „Imię” przy rejestracji).

**Mapa dojazdu (szczegóły wydarzenia):** osadzona mapa Google z trasą komunikacją miejską (Maps Embed API). Start trasy to lokalizacja z przeglądarki, gdy użytkownik się zgodzi, a bez zgody dzielnica z profilu; do naszego API lokalizacja nie trafia. Bez klucza strona pokazuje sam przycisk do Map Google. Klucz:
1. W [Google Cloud Console](https://console.cloud.google.com/) utwórz projekt z podpiętym kontem rozliczeniowym (Maps Embed API jest bezpłatne, ale Google Maps Platform wymaga rozliczeń).
2. *APIs & Services → Library*: włącz **Maps Embed API**.
3. *APIs & Services → Credentials → Create credentials → API key*, a potem w ustawieniach klucza:
   - *Application restrictions → Websites*: `https://portal.waw-out.pl/*` i `http://localhost:8000/*`;
   - *API restrictions*: tylko **Maps Embed API**.
4. Klucz trzymamy w SSM (`terraform output google_maps_embed_key_parameter`, domyślnie `CHANGE_ME` = sama mapa wyłączona):
   ```sh
   aws ssm put-parameter --name /codzis/google-maps-embed-key --type SecureString --overwrite --value "AIza..."
   terraform -chdir=infra apply      # wstawia klucz do config.js
   ```
   Klucz trafia do publicznego `config.js`, więc ograniczenia z punktu 3 są obowiązkowe.

**API** (HTTP API, ID token Cognito w `Authorization: Bearer …`, weryfikuje go API Gateway):

| Endpoint | Opis |
| --- | --- |
| `GET /api/me` | profil (pierwsze wywołanie zakłada rekord i dane konta), `account`, `needsOnboarding`, `onboardingOutdated` |
| `PUT /api/me` | `{"birthDate"}` → dane konta (imię i nazwisko się nie zmieniają); pusta data = usuń; przy wypełnionej ankiecie przelicza preferencje (przedział wieku) |
| `POST /api/me/photo` | `{"contentType"}` → `{key, upload}`: presigned POST, przeglądarka wysyła zdjęcie prosto do S3 |
| `PUT /api/me/photo` / `DELETE /api/me/photo` | `{"key"}` → wgrane zdjęcie staje się profilowym (stare usuwamy) / profil bez zdjęcia |
| `GET /api/onboarding` | kafelki z pytaniami (ikony, limity wyborów, wymagane pola) |
| `PUT /api/profile` | `{"answers": {"who": ["kids"], ...}}` → walidacja, preferencje, zapis |
| `GET /api/events/{id}/crew` | czat mojej ekipy (tylko zapisani): pierwsze wejście dołącza do ekipy, `?after=<cursor>` = tylko nowe wiadomości, każde wejście oznacza przeczytane |
| `POST /api/events/{id}/crew/messages` | `{"text"}` (1-500 znaków) → wiadomość do mojej ekipy; `429 too_fast` częściej niż co 1 s |
| `GET /api/me/crews` | moje ekipy: nieprzeczytane, ostatnia wiadomość, skład (plakietki i „Twoje”) |
| `GET /api/recommendations` | `?when=today\|tomorrow\|weekend\|week\|date&date=2026-10-30&q=jazz&limit=16` → karty wydarzeń z uzasadnieniem (sekcja Rekomendacje); `202 {"status": "preparing"}` gdy zestaw właśnie się liczy, `409` bez profilu, `503` zanim powstanie indeks |

**Onboarding:** pytania i mapowanie odpowiedzi są w jednym miejscu, `src/client_api/onboarding.py`; frontend tylko je wyświetla. Jest 9 kafelków:
- wymagane: z kim, klimat (maks. 2), co odkryć (maks. 2), gdzie (dzielnica i zasięg);
- opcjonalne: sprawy miejskie, kiedy, budżet, formuła (na żywo / online, zapisy), o Tobie (kilka zdań o sobie, dostępność).

Pola: `single`, `multi` (limit `maxSelect`), `select` i `text`, czyli wolny opis „Kilka zdań o sobie”: do 300 znaków, odpowiedź `["tekst"]`. Backend usuwa znaki sterujące i zbędne odstępy, opis trafia do preferencji jako `about` i na koniec `ragProfile`. Czyta go tylko ranking DeepSeek (`recommender/ranker.py`), wyszukiwanie wektorowe go nie używa.

Wieku nie ma w ankiecie. Przedział (`ageRange`: `under18`, `18-29`, `30-49`, `50-64`, `65+`, w `ragProfile` jako `age=…`) i grupę odbiorców dopisaną do `audience` liczymy z daty urodzenia w danych konta (`with_age` w `onboarding.py`). Dzieje się to przy zapisie ankiety i przy zmianie daty: `PUT /api/me` przelicza wtedy preferencje i `ragProfile`, a gdy zmieni się przedział, zleca nowe rekomendacje. Bez daty urodzenia profil jest bez wieku.

**Czat ekipy** (`src/client_api/crews.py`, tabela `codzis-crews`): zapisani na wydarzenie łączą się w ekipy do 4 osób (pierwsza ekipa z wolnym miejscem, gdy brak - nowa), każda ma własny czat. Komunikaty Wodzireja (powitanie z lodołamaczem, dołączenie, wyjście, komplet) powstają z danych wydarzenia, bez LLM, a treść rozmów nie wychodzi poza AWS. Wypisanie z wydarzenia = wyjście z ekipy (wiadomości zostają), pusta ekipa się zamyka. Bez WebSocketów: otwarty czat pyta API co 3 s o nowe wiadomości, plakietki nieprzeczytanych co 30 s (tylko przy widocznej karcie). Nieprzeczytane to liczniki w rekordach ekipy i członka, aktualizowane w tej samej transakcji co wiadomość. Dane znikają same (TTL) 30 dni po końcu wydarzenia.

**Rekord użytkownika (tabela `codzis-users`, klucz `userId` = `sub` z Cognito, PITR włączone):**

| Pole | Opis |
| --- | --- |
| `email`, `displayName`, `picture`, `identityProvider` | z tokenu (`Google` / `Cognito`); `displayName` = imię (z rejestracji albo `given_name` z Google), niezmienne; `familyName` = nazwisko (opcjonalne przy rejestracji, z Google), innym tylko inicjał („Ola K.”) |
| `account` | dane konta z profilu: `birthDate` (RRRR-MM-DD, widzi ją tylko właściciel; z niej przedział wieku w `preferences.ageRange`), `photoUrl`, `photoKey`; zakładane przy pierwszym logowaniu (z Google zdjęcie), potem zmienia je tylko użytkownik. Zdjęcia: bucket zdjęć, `photos/avatars/<userId>/…`, zmniejszone w przeglądarce do 512 px |
| `onboarding` | `{version, completedAt, answers}`: surowe odpowiedzi; zmiana pytań zmienia `version` |
| `preferences` | odpowiedzi przemapowane na słownik eventów: `themes`, `formats`, `audience`, `occasion`, `activityLevel`, `cost`, `mode`, `setting`, `registration`, `accessibility` (opcje taksonomii taggera), `interests` (kategorie kalendarza UM), `days`/`timeOfDay`/`weekend` (jak `facets` eventów), `district`, `travelRange`, `maxPrice`, `ageRange` (z daty urodzenia), `about` (wolny opis z ankiety) |
| `ragProfile` | tekst pod RAG, np. `interests=[Czas wolny, Kultura] \| district=Śródmieście \| cost=Bezpłatne \| mode=Stacjonarne \| audience=Dorośli (18-64) \| … \| age=30-49 \| about=Lubię jazz…` (w opisie `\|` zamieniamy na `/`) |

**Lokalny development** na wdrożonej infrze:
- `scripts/frontend-dev.sh client` (http://localhost:8000; adres jest w callbackach Cognito i w CORS API);
- `scripts/frontend-dev.sh partner` (http://localhost:8001; `/api` idzie przez proxy do domeny panelu).

Testy frontendu: `npm --prefix src/frontend test`.

## Rekomendacje (RAG)

Zakładka **Rekomendacje** w portalu klienta: wybór dnia (dziś / jutro / weekend / 7 dni / inny dzień do 60 dni naprzód), wyszukiwanie tekstem („jazz”, „joga”), kategorie i karty jak w makiecie (cena, miejsce, termin, „Pasuje: …”, Trasa, Bilet / Szczegóły). Silnik to pakiet [`recommender/`](recommender) z brancha `llm`, dostosowany do schematu v1 eventów.

**Zapisane zestawy (tabela `codzis-recommendations`):** rekomendacje liczą się raz i są zapisywane per użytkownik (`userId` + okno i daty). Ponowne wejście, przełączanie dni i odświeżanie strony czytają zapis. **Wyszukiwanie frazą jest wspólne dla dzielnicy:** zestaw z `q` ma `userId` = `search#<dzielnica z profilu>` i liczy się tylko z frazy, dzielnicy i terminu (bez reszty profilu, `user_context.search_prefs`). Pierwsza osoba z dzielnicy liczy go (wektory od razu, potem AI w tle), każda następna dostaje gotowy wynik z AI od razu, także na zimnej instancji. Fraza w kluczu: małe litery, pojedyncze spacje; zestaw jest świeży 12 h (`RESULTS_MAX_AGE`), potem przelicza się w tle przy wejściu.
- **Z góry** liczą się zestawy na dziś, jutro i najbliższy weekend:
  - w nocy dla osób aktywnych w ostatnich 14 dniach (`recommender_precompute_schedule`, domyślnie 3:00 UTC);
  - od razu po zmianie preferencji (client-api wywołuje rekomender asynchronicznie);
  - przy logowaniu, jeśli któregoś brakuje.
- **Na żądanie** liczy się inny dzień i wyszukiwanie frazą, potem też z zapisu.
- **Odświeżanie:** zestaw starszy niż 12 h (`recommender_results_max_age_hours`, żeby złapać nowe eventy) albo z małą liczbą trwających jeszcze wydarzeń pokazuje się od razu i jednocześnie liczy się od nowa w tle (`"updating": true`). Zakończone wydarzenia znikają z kart same. Czekać trzeba tylko wtedy, gdy zestawu jeszcze nie ma albo zmienił się profil (`202 preparing`, strona dopytuje co 2 s).
- **Liczenie zawsze w tle** (GET zleca je asynchronicznie tej samej Lambdzie, więc nie ogranicza go limit 30 s HTTP API), w dwóch fazach: najpierw filtry + wektory (sekundy, zestaw od razu do zapisu, bez LLM), potem DeepSeek (do 60 s, dla dziś / jutro / weekend równolegle): przy wpisanej frazie najpierw ją rozwija (`recommender/expand.py`, np. „coś na randkę” → konkretne rodzaje wydarzeń) i kandydaci są wybierani jeszcze raz, potem układa kolejność i pisze uzasadnienia. Strona sama podmienia listę, gdy wersja z AI jest gotowa.
- **Bez dublowania:** liczony zestaw dostaje claim w tabeli, więc drugi chętny czeka, zamiast liczyć to samo; claim wygasa po 3 min, gdyby liczenie padło. Strona po pierwszym zestawie dociąga w tle pozostałe z dziś / jutro / weekend.

**Jak dobieramy propozycje** (`src/recommender_api/user_context.py` mapuje `preferences` z onboardingu):
1. **Twarde filtry:** termin w wybranym oknie (już zakończone odpadają; zajęcia cykliczne wg dni tygodnia), dzielnica wg zasięgu dojazdu (okolica / sąsiednie dzielnice / cała Warszawa), koszt („tylko bezpłatne”), forma (na żywo / online), grupa odbiorców, budżet.
2. **Podobieństwo wektorowe:** model `paraphrase-multilingual-mpnet-base-v2` (768 wymiarów, lokalnie, CPU) porównuje profil (tematy, formaty, kategorie) albo wpisaną frazę z tekstem eventu (tytuł, kategorie, tagi AI, opis). Słabe dopasowania (podobieństwo < 0,30, `DEFAULT_MIN_SCORE`) odpadają, więc zestaw może mieć mniej niż 16 kart zamiast dopełnienia szumem.
3. **Miękkie preferencje:** drobne punkty za zgodność tagów i drobne kary za sprzeczność (np. pora dnia poza wybraną, online bez prośby o online) (tematy, formaty, z kim, aktywność, plener / pod dachem, zapisy, dostępność), porę dnia, bliskość dzielnicy; mniej za „wydarzenia” trwające miesiącami (to zwykle programy, nie propozycja na dziś). Potem dedupe tytułów i różnorodność (nie 5 kart z jednej pływalni).
4. **DeepSeek** (opcjonalnie, ten sam klucz co tagger): układa najlepszych kandydatów (tylu, ile kart prosi strona: 16) i pisze uzasadnienia. Przy błędzie lub po 60 s zostaje kolejność wektorowa z uzasadnieniem z reguł.

Gdy w okolicy wyjdą mniej niż 4 propozycje, obszar poszerza się sam (strona to pokazuje).

**Indeks:** `s3://<data_bucket>/recommender/index.npz` (wektory + odchudzone eventy). EventBridge co 30 min (`recommender_refresh_minutes`) skanuje tabelę `events` i liczy embeddingi tylko dla nowych lub zmienionych tekstów. Nowe eventy trafiają do zapisanych zestawów przy ich kolejnym przeliczeniu (najpóźniej po 12 h). Drugi harmonogram co 5 min trzyma model w pamięci (`recommender_keep_warm`), bo zimny start z torchem i modelem mpnet trwa kilkadziesiąt sekund. Koszt: grosze miesięcznie (Lambda płatna za czas wywołań, ECR ~0,30 USD/mies. za obraz ~3 GB).

**Zmiana modelu embeddingów** (`DEFAULT_MODEL` w `recommender/embedder/model.py` = `EMBEDDING_MODEL_NAME` w `src/recommender_api/Dockerfile`): wektory starego modelu nie pasują do nowego, więc po `scripts/push-images.sh recommender` od razu uruchom `scripts/recommender-refresh.sh` (pełny reindeks, przy ~1200 eventach z mpnet ok. 5-10 min). Do tego czasu rekomender odrzuca indeks z innym modelem: zapisane zestawy dalej się wyświetlają, a nowe liczą się dopiero po przebudowie (najpóźniej przy harmonogramie co 30 min). Podbicie `RESULTS_VERSION` w `results_store.py` sprawia, że zapisane zestawy są pokazywane, ale przeliczane w tle przy najbliższym wejściu.

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

Kod: `run_task.py` + `tagger/` ([tagger/README.md](../tagger/README.md)), obraz z `Dockerfile` w katalogu głównym.

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
- **Zdjęcia w standardzie** (`tagger/images.py`, bez LLM): tagger pobiera zdjęcie źródłowe i zapisuje WebP 3:2 do 1200×800 (jakość 82, sRGB, bez metadanych) w buckecie zdjęć: `photos/events/v2/<sha1 adresu>.webp`, publicznie `https://<domain_name>/photos/…`. W rekordzie `imageUrl` = nasz plik, `sourceImageUrl` = źródło; ten sam adres źródła = ten sam plik. Od 4:3 do 16:9 zdjęcie wypełnia kadr (z brzegu znika najwyżej 8%) w rozdzielczości najwyżej 2× źródła (miniatura UM 360×270 -> 720×480); plakaty pionowe, kwadraty i panoramy są całe, powiększone najwyżej 2×, na jednolitym polu 3:2 w kolorze brzegu zdjęcia. Nieudane zdjęcie nie blokuje zapisu (zostaje adres źródłowy). Pobieranie tylko https z publicznych adresów, do 15 MB / 25 Mpx.
- **Zdjęcia wydarzeń już w tabeli** (po pierwszym wdrożeniu i po zmianie standardu = nowy `VERSION`): `scripts/resize-images.sh` (`--dry-run`: tylko przeliczenie, `--limit N`). Lokalnie w Dockerze z twoimi credentialami; można powtarzać (gotowe pliki są pomijane); zdjęcia usunięte w UM (404) liczy osobno jako `brak u źródła`, kod wyjścia `2` = inne błędy. Portal pokazuje nowe adresy po odświeżeniu pamięci client-api (5 min) i indeksu rekomendera (30 min); zapisane zestawy rekomendacji przy najbliższym przeliczeniu (w nocy).
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
| `imageUrl`, `attributes` | zdjęcie po https (w tabeli: plik w standardzie zdjęć, patrz Tagger); dodatki specyficzne dla źródła |
| `sourceImageUrl` | dopisuje tagger: adres źródłowy zdjęcia (z niego powstaje plik w standardzie) |
| `contentHash`, `importedAt` | wykrywanie zmian w importerze |
| `declared` | tylko partner: koszt, wejście, miejsce, dla kogo, dostępność podane w formularzu; tagger przepisuje je do `tags` zamiast zgadywać |
| `tags` | dopisuje tagger: 10 wymiarów z `tagger/prompt.py` |
| `facets` | dopisuje tagger, z danych: `timeOfDay`, `days`, `weekend`, `multiDay`, `recurring` |
| `tagInputHash`, `taxonomyVersion`, `expiresAt` | tagger: wykrywanie zmian dla modelu, wersja taksonomii, TTL (epoch) |

Pola portalu partnera i ich walidacja: `TEXT_FIELDS`, `DECLARED_FIELDS` i `_event_input` w `src/api/events.py`. Opcje w `DECLARED_FIELDS` muszą być dokładnie opcjami z `tagger/prompt.py` (wartość spoza taksonomii tagger pominie); portal pobiera je z `GET /api/me` (`formOptions`). Cena (`priceMin`/`priceMax`, tylko przy „Płatne”) i link do biletów lądują w `attributes`. Kategorie: zmienna `event_categories`, dzielnice: `local.warsaw_districts`.

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

- Bez logowania Google klucz API to jedyny "login". Partner musi go chronić jak hasło, nie ma też resetu ani wygasania (poza usunięciem klucza).
- Z Google konto organizatora może założyć każdy (samoobsługa, bez weryfikacji instytucji); ogłoszenia podpisuje imię i nazwisko z konta Google.
- Klucze trafiają do state'u Terraforma (lokalnie, plaintext).
- Mock bramka: `confirm` woła sam partner, więc każdy zalogowany może dodać sobie kredyty. Przy prawdziwej bramce (np. Stripe, PayU, Przelewy24) zastąp to webhookiem od operatora, weryfikowanym podpisem.
- Kredyt jest pobierany przy zapisie ogłoszenia, przed uploadem zdjęcia. Jeśli upload się nie uda, `image.highlighted.path` wskazuje na nieistniejący plik.
- Czas z formularza jest interpretowany w strefie przeglądarki partnera.
- **Domena główna bez subdomeny** (np. samo `waw-out.pl`) nie zadziała z CloudFront przez home.pl: CNAME wymaga hosta, a rekord A wymagałby stałego IP, którego CloudFront nie ma. Dlatego obie strony są na subdomenach (`partner.`, `portal.`).
- Rekomendacje: nowy event trafia do indeksu w ciągu 30 min, a do zapisanych zestawów przy ich przeliczeniu (najpóźniej po 12 h); sąsiedztwo dzielnic jest przybliżone; brak jeszcze sygnałów zwrotnych (polubienia → `liked_event_ids`), które recommender już obsługuje.
- Nocne przeliczenie to jedno wywołanie Lambdy (do 15 min, ~15-25 s na osobę z LLM): wystarczy na kilkadziesiąt aktywnych osób, przy większej skali trzeba je rozłożyć (np. SQS).
- Liczenie zestawu po zimnym starcie Lambdy rekomendera czeka dodatkowe kilkadziesiąt sekund na model (zapisane zestawy podaje bez modelu, od razu); harmonogram „warmup” zwykle temu zapobiega.
- Pełny reindeks (po zmianie modelu) przy ~1200 eventach trwa ok. 5-10 min z limitem Lambdy 15 min; przy ~2× większej bazie trzeba go będzie dzielić albo puszczać lokalnie.
- Ogłoszenie partnera pojawia się w tabeli `events` po ~2-5 min (start kontenera + tagowanie).
- Brak alarmu na DLQ: zepsute wiadomości trzeba sprawdzać ręcznie.
- Rekordy usunięte w źródle przed końcem (np. odwołane eventy) zostają w tabeli do `expiresAt`; zajęcia cykliczne usunięte w źródle zostają na stałe (importer tylko loguje ich liczbę).
- Zmiana taksonomii przetaguje tylko rekordy, które przyjdą ponownie; żeby przetagować wszystko: pełne przeładowanie (sekcja Initial load).
- API GW jest też dostępne bezpośrednio pod `execute-api` (z tym samym kluczem).
