# Znajomi — projekt

Data: 2026-10-18 (noc przed demo). Właściciel: Dawid. Bazuje na `2026-10-18-community-explore-design.md` (zapisy, „Kto się wybiera”, imię) i na zakładce „Twoje” (gałąź `feat/twoje-wydarzenia`: moje zapisy + czaty ekipy).

## Po co
Zapis na wydarzenie jest dziś anonimowy dla ludzi, których znasz: widzisz imiona obcych, ale nie wiesz, gdzie idą Twoi. Chcemy, żeby wydarzenia były okazją do spotkania z bliskimi — „społecznie zacieśniać więzi”. Dodajesz znajomego kodem albo QR, a potem widzisz, na co się zapisuje, i jednym kliknięciem idziesz z nim.

## Cele
- **Kod i QR:** każdy użytkownik ma krótki kod do podyktowania (np. `WAW-7K2P`) i kod QR. QR to zwykły link do portalu z kodem (np. `https://portal.waw-out.pl/#/znajomi/dodaj/WAW-7K2P`): skanuje się go aparatem telefonu, portal otwiera ekran „Wysłać zaproszenie do <Imię>?”. Kod można też wpisać ręcznie w aplikacji.
- **Zaproszenie z akceptacją:** dodanie po kodzie wysyła zaproszenie; właściciel kodu akceptuje albo odrzuca (decyzja Dawida — ochrona przed nadużyciem wyciekłego kodu). Po akceptacji znajomość jest **obustronna**.
- **Usuwanie:** znajomego można usunąć w każdej chwili (obie strony przestają widzieć swoje zapisy). Kod można wygenerować na nowo (stary przestaje działać; istniejący znajomi zostają).
- **Zakładka „Znajomi”** (zastępuje Eksploruj w nawigacji):
  - u góry **wydarzenia, na które idą znajomi** (nadchodzące), każde z „Ola i Kuba idą” i przyciskiem **„Idę też”** (istniejący zapis) albo stanem „Zapisano”;
  - niżej **lista znajomych** z ich najbliższymi zapisami, **zaproszenia** do akceptacji, mój kod + QR, pole „Wpisz kod”, usuwanie;
  - **pusty stan** (zero znajomych): duży mój QR, „Pokaż znajomemu albo wpisz jego kod”.
- **Wszędzie indziej:** na kartach (Dla Ciebie, Wszystkie, Popularne, Twoje) linijka „Ola idzie” / „Ola i 2 innych znajomych idzie”; w „Kto się wybiera” znajomi na górze.
- **Nawigacja:** Dla Ciebie · Znajomi · Popularne · Twoje · Profil.
- **Eksploruj znika z menu:** na końcu listy „Dla Ciebie” (i w jej pustym stanie) link **„Nie pasuje? Zobacz wszystkie wydarzenia”** prowadzi do dotychczasowego widoku z filtrami (trasa `/eksploruj` zostaje, tylko bez pozycji w menu).
- **Imię obowiązkowe:** konto bez imienia (konta sprzed 18.10) podaje je **jednorazowo zaraz po zalogowaniu** (istniejący `NameDialog` + `setMissingName`), a nie dopiero przy pierwszym zapisie — znajomi muszą wiedzieć, kogo dodają. Imienia potem nie zmieniamy.
- **Demo:** konto Dawida ma 2–3 znajomych z zapisami na nadchodzące wydarzenia (konta zespołu albo wyraźnie oznaczone osoby testowe `seed: true`, usuwalne skryptem).

## Nie-cele
Wyszukiwanie ludzi po imieniu/e-mailu, import kontaktów, profil znajomego z historią, „znajomi znajomych”, powiadomienia push i e-mail, czat 1:1 (czat jest per wydarzenie — ekipa), wydarzenia minione znajomych.

## Anty-cele
- **Nikt bez akceptacji nie widzi moich zapisów.** Wysłanie zaproszenia nie daje wglądu w nic poza imieniem właściciela kodu.
- **Nigdy e-maili** — wszędzie tylko imię.
- **Nie śledzimy ludzi:** znajomi widzą tylko nadchodzące zapisy, bez historii.
- Kod nie daje się zgadnąć w praktyce (losowy, nie sekwencyjny), a zbyt wiele prób wpisania złego kodu jest blokowane/limitowane.

## Ograniczenia
- Stack i zasady z `AGENTS.md`: client-api (Python, `src/client_api`, moduły + cienki `handler.py`, `ApiError`, pytest + moto), DynamoDB projektowane od zapytań (klucze/GSI per zapytanie, bez scan w ścieżce żądania poza istniejącym wyjątkiem cache wydarzeń), tabele w Terraformie, jeden zapisujący per tabela (client-api), front TanStack Router + Query + Zod, Tailwind/shadcn, bez AI slop.
- **Zależności:** generowanie QR wymaga małej biblioteki (w projekcie jej nie ma) — jedna, mała, bez zależności; skanowania QR w aplikacji **nie budujemy** (robi to aparat telefonu, bo link).
- Zapisy znajomych bierzemy z istniejącej tabeli `codzis-attendance` (GSI `byUser`). Imię znajomego z claimu `name` w chwili akcji albo z `codzis-users.displayName`.
- Wdrożenie przez Terraform (Dawid uruchamia `apply`; Claude przygotowuje plan). Kod zamrożony 07:00, demo 11:30 — **Znajomi wchodzą po „Twoje”** (ta sama nawigacja; zmiana menu po zmergowaniu `feat/twoje-wydarzenia`).
- Testy: `scripts/backend-check.sh`, vitest dla logiki frontu.

## Decyzje po przeglądzie (decyzje Claude, do sprawdzenia przez Dawida)
1. **Dane:** nowa tabela `codzis-friends` (zapisuje tylko client-api), w jednym `terraform apply` razem z trasami. Kod użytkownika jako osobny rekord „kod → użytkownik” (odczyt po kluczu, nigdy scan). Nowa tabela o tej porze jest akceptowalna — wdrożenie i tak idzie przez plan + apply.
2. **Imiona znajomych kopiujemy** do rekordu znajomości w chwili zaproszenia/akceptacji (imię jest niezmienne, więc kopia się nie zestarzeje). Brak imienia nie może się zdarzyć: konto bez imienia musi je podać po zalogowaniu, zanim zobaczy swój kod lub wyśle zaproszenie (API odrzuca akcję bez imienia).
3. **„Ola idzie” bez N+1:** limit **50 znajomych** na MVP. Front pobiera **jedną mapę** „wydarzenie → imiona znajomych” (jedno wywołanie na ekran, np. `GET /api/friends/going`) i dokleja ją po stronie klienta do wszystkich list, także kart rekomendacji. Rekomendera (`src/recommender_api/`, `recommender/`) nie ruszamy.
4. **QR generuje front** (mała biblioteka npm — zgoda w tym dokumencie). Adres w QR z `window.location` (origin + ścieżka), nie wpisany na sztywno.
5. **Stany zaproszeń:** zaproszenie do siebie → błąd; A zaprasza B, gdy B ma już oczekujące zaproszenie do A → **automatyczna akceptacja**; ponowne zaproszenie po odrzuceniu lub usunięciu → dozwolone; odrzucenie jest **ciche** (zapraszający widzi tylko „oczekuje” do czasu wygaśnięcia albo do akceptacji); usunięcie znajomości kasuje ją u obu stron.
6. **Limit złych kodów:** licznik na użytkownika w DynamoDB z TTL (np. 10 błędnych prób na godzinę → 429 z polskim komunikatem). Throttling API Gateway zostaje jak jest.
7. **Nowy kod:** oczekujące zaproszenia wysłane starym kodem **zostają ważne**; stary kod przestaje działać dla nowych zaproszeń; istniejący znajomi zostają.
8. **Demo:** rozszerzenie `scripts/seed_demo.py` o tryb dla wskazanego konta (np. `--friends-of <e-mail>`, `sub` odczytany z Cognito tylko do odczytu): 3 znajomych testowych `seed-…` (zaakceptowani, `seed: true`, usuwalni `--delete`) z zapisami na nadchodzące wydarzenia. Na scenie zespół może dodatkowo dodać się na żywo przez QR — to moment pokazu.

## Zostawione budowniczemu
Model danych (np. tabela `codzis-friends` z parą użytkowników i statusem + mapowanie kod → użytkownik), dokładne trasy API i kształty odpowiedzi, format i długość kodu, sposób limitowania prób, biblioteka QR, wygląd sekcji i kart, sposób dociągania „Ola idzie” do kart (jedno zapytanie na ekran), mechanizm danych demo (rozszerzenie `scripts/seed_demo.py`).
