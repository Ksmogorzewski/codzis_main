# Front WarsawNow (`src/frontend/`)

Jeden projekt Vite, dwie aplikacje: **portal klienta** (`client/`, tryb `client`) i **panel partnera** (`partner/`, tryb `partner`). Ten plik opisuje portal klienta. **Pilnuj struktury opisanej niżej**; jeśli zmiana jej nie pasuje, zatrzymaj się i zapytaj, zamiast tworzyć nowy wzorzec. Panelu partnera nie zmieniaj bez zgody Krzysztofa.

## Produkt (portal klienta)
Logowanie (Cognito: e-mail + hasło, rejestracja z kodem z e-maila, reset hasła; albo „Kontynuuj z Google” przez Hosted UI) → ankieta z kroków `GET /api/onboarding` → propozycje z `GET /api/recommendations` (filtr czasu dziś/jutro/weekend/7 dni/inny dzień, wyszukiwarka, kategorie, odległość z geolokalizacji, uzasadnienie „Pasuje: …”) → szczegóły wydarzenia (`GET /api/events/{id}`: pełny opis, lista zapisanych, mapa Google z trasą komunikacją miejską). **Eksploruj** (`GET /api/events`: wszystko w oknie czasu, bez profilu), **Popularne w najbliższym tygodniu** (`GET /api/popular`, dziś + 6 dni), **Zapisz / Zapisano** na kartach i w szczegółach. **Twoje** (`GET /api/me/events`): wydarzenia, na które jestem zapisany — „Nadchodzące” i „Minione”, przy każdym „Zapisano” (wypisanie od razu usuwa z listy) i wiersz „Czat ekipy” z ostatnią wiadomością i liczbą nieprzeczytanych. **Znajomi** (`GET /api/friends`, `/api/friends/going`; trasy w `src/client_api/routes/friends.py`): u góry „Znajomi idą” (nadchodzące wydarzenia znajomych, „Idę też” = `SaveButton`), „Zaproszenia” (Akceptuj/Odrzuć), „Twoi znajomi” (najbliższy zapis, Usuń z potwierdzeniem), „Twój kod” (kod `WAW-XXXXXX` + QR z linkiem `#/znajomi/dodaj/<kod>` z `window.location`, „Kopiuj link”, „Nowy kod”), „Wpisz kod znajomego”; bez znajomych duży QR. `#/znajomi/dodaj/<kod>` → „Wysłać zaproszenie do <Imię>?” (bez sesji przez `/login?redirect=…` i z powrotem). Na kartach wszystkich list linijka „Ola idzie” (`FriendsLine`, jedno zapytanie `friends-going` na ekran), w „Kto się wybiera” znajomi z ikonką na górze. **Osoby rozpoznajemy po `userId`, nigdy po imieniu** (dwie „Ole” to dwie osoby): `friends/going` zwraca znajomych jako `{userId, name}`, `attendees` ma `userId` w `people[]`; klucze React, „najbliższy zapis” (`nearestFor`) i skład ekipy czatu (`members`: `{userId, name}` z API czatu) idą po id. QR rysuje `components/friends/qr-code.tsx` z macierzy biblioteki `uqr` (bez zależności, wersja przypięta). Eksploruj nie ma pozycji w menu — link „Nie pasuje? Zobacz wszystkie wydarzenia” na końcu Dla Ciebie. Nawigacja: Dla Ciebie / Znajomi / Popularne / Twoje / Profil (nagłówek na desktopie — między 768 a 1100 px same ikony; dolny pasek na telefonie, 5 zakładek od 360 px); „Twoje” z plakietką sumy nieprzeczytanych, „Znajomi” z plakietką liczby zaproszeń (`hooks/use-friend-invites.query.ts`: `incoming` z `GET /api/friends` pod osobnym kluczem `friendInvitesKey`, co 30 s i po powrocie do karty na każdym ekranie; `409 name_required` → 0 bez prośby o imię; powyżej 9 „9+”; ta sama `UnreadBadge`). **Profil**: dane konta (`PUT /api/me`, zdjęcie `/api/me/photo`: zmniejszone w przeglądarce, presigned POST do S3; imię i nazwisko tylko do odczytu, data urodzenia widoczna tylko dla właściciela) i ankieta. Wygląd: kierunek „Plakat” (polska szkoła plakatu: papier, atrament, płaskie kolory kategorii, ostre rogi).
**Imię:** wymagane przy rejestracji (atrybut Cognito `name`; walidacja `NameSchema` w `lib/auth-form.ts`: litery, spacje, myślnik, maks. 40), potem niezmienne; opcjonalne **nazwisko** przy rejestracji (atrybut `family_name`, wysyłany tylko niepusty, `FamilyNameSchema` — te same reguły, niezmienne, bez pola w profilu); innym pokazujemy tylko „Ola K.” (backend `display_name`, front `displayName` / `currentDisplayName()` w `lib/auth.ts` dla „(Ty)” i „Zapisano jako …”); konta bez imienia dostają jednorazową prośbę zaraz po zalogowaniu (`NameDialog required` w `_app.tsx`, bez zamykania; też po `409 name_required` z tras znajomych przez `lib/name-prompt.ts`) i przed pierwszym zapisem (`setMissingName` w `lib/auth.ts`). Na listach zapisanych tylko imię (brak → „Ktoś”; backend bierze imię z tokenu, a bez niego `displayName` z `codzis-users`), nigdy e-mail. Po zapisie mój wpis „<Imię> (Ty)” pojawia się od razu (imię z ID tokenu), toast „Zapisano jako <Imię>”.
**Czat ekipy** (backend: `src/client_api/crews.py`, trasy `GET /api/events/{id}/crew`, `POST …/crew/messages`, `GET /api/me/crews`): zapisani łączą się w ekipy do 4 osób (pierwsze wejście na czat dołącza do ekipy z wolnym miejscem albo zakłada nową), każda ma własny czat. W szczegółach pod „Kto się wybiera” sekcja „Ekipa na to wydarzenie” (`components/crew/crew-entry.tsx`): zapisani widzą „Wejdź na czat” i skład ekipy, pozostali „Zapisz się, żeby dołączyć do czatu ekipy” (ten sam `useSave`). Czat: `#/wydarzenie/<id>/ekipa` (`routes/_app/wydarzenie.$id_.ekipa.tsx` → `components/crew/crew-chat-screen.tsx`; na telefonie pełny ekran nad paskiem zakładek, na desktopie karta) — lodołamacz zasłania czat, dopóki nic nie napiszę (`answered`), wiadomości osób z godziną, komunikaty Wodzireja („welcome”, „joined”, „left”, „full”) składane w `lib/crew-chat.ts` z danych wydarzenia: punkt i czas zbiórki tylko z miejsca i terminu, **bez LLM i bez zmyślonych odpowiedzi**; „Pokaż Kartę Koloru” → „JESTEM TUTAJ”, gdy w ekipie są co najmniej 2 osoby. **Bez WebSocketów:** `hooks/use-crew.query.ts` pyta co 3 s (tylko widoczna karta) z `?after=<cursor>` i łączy odpowiedzi po id (`mergeCrew`; serwer oddaje 15 s zapasu), wysyłka `hooks/use-send-message.mutation.ts` dokłada wiadomość od razu (`withMessage`), błędy (np. `429 too_fast`) jako toast z tekstem z powrotem w polu. Wypisanie z wydarzenia = wyjście z ekipy (`useSave` usuwa zapamiętany czat).
**Nieprzeczytane:** `hooks/use-my-crews.query.ts` (`GET /api/me/crews`, co 30 s i po powrocie do karty) — plakietka „Twoje” (`hooks/use-crew-unread.ts`), wiersz „Czat ekipy” na „Twoje” z ostatnią wiadomością (`crew-chat-row.tsx`) i toast „Nowa wiadomość w czacie: <tytuł>” z „Otwórz” (`components/crew/new-message-toasts.tsx`, montowany w `_app.tsx`; nie na ekranie tego czatu; bez powiadomień przeglądarki). Otwarty czat oznacza wszystko jako przeczytane (serwer) i od razu zeruje plakietkę tej ekipy (`markCrewRead`).
**Poza zakresem bez zgody zespołu:** „Sponsorowane”, pogoda, czat w czasie rzeczywistym (WebSocket) i „X pisze…”.

## Komendy (z `src/frontend/`)
```sh
npm ci
npm run dev:client      # http://localhost:8000 (wymaga client/public/config.js — patrz niżej)
npm test                # vitest
npm run typecheck       # tsc
npm run build           # typecheck + build klienta i partnera do dist/
```
`config.js` lokalnie: `scripts/frontend-dev.sh client` (z katalogu repo; generuje go z `terraform output`, wymaga dostępu do AWS) albo ręcznie `client/public/config.js` z `window.APP_CONFIG = {…}` od Krzysztofa (plik jest w `.gitignore`). `localhost:8000` jest w CORS API i adresach Cognito — nie zmieniaj portu.
Wdrożenie: `scripts/build-frontend.sh`, potem `terraform apply` (wgrywa `dist/client` do S3).

## Stos
React 19 · TypeScript (strict, bez `any`) · TanStack Router (trasy plikowe, **historia na `#`** — CloudFront nie ma fallbacku SPA) · TanStack Query · Zod · Tailwind 4 + shadcn/ui (Radix) · Sonner · vitest. Cognito przez `fetch` (bez SDK).
**Nowa zależność = pytanie do zespołu.** Najpierw sprawdź, czy da się bez niej.

## Struktura (`client/`)
```
main.tsx                 QueryClient (retry tylko błędów przejściowych), router (createHashHistory), kontekst { queryClient, auth }
routes/                  trasy plikowe; routeTree.gen.ts jest GENEROWANY — nie edytuj
  __root.tsx             obudowa, not found → /
  login.tsx              logowanie / rejestracja / kod / reset hasła
  _app.tsx               strażnik sesji (beforeLoad: requireSession, powrót po logowaniu), prośba o imię
  _app/index.tsx         Dla Ciebie: propozycje (search params: when, date, q, cat)
  _app/eksploruj.tsx     Eksploruj (search params: when, date, cat, district, free, indoor, q — lib/explore.ts)
  _app/popularne.tsx     Popularne w najbliższym tygodniu
  _app/twoje.tsx         Twoje wydarzenia: moje zapisy + czaty ekip (nieprzeczytane z GET /api/me/crews)
  _app/znajomi.tsx       Znajomi: znajomi idą, zaproszenia, lista, mój kod + QR, „Wpisz kod”
  _app/znajomi_.dodaj.$code.tsx  ekran z linku w QR: zaproszenie do właściciela kodu („_” = poza układem /znajomi)
  _app/profil.tsx        ankieta
  _app/wydarzenie.$id.tsx szczegóły (+ lista zapisanych)
  _app/wydarzenie.$id_.ekipa.tsx czat ekipy (tylko dla zapisanych; bez loadera - pierwsze zapytanie dołącza do ekipy)
components/<obszar>/     auth, account (dane konta w profilu: zdjęcie, imię i nazwisko do odczytu, data urodzenia), events, explore, popular, my-events (Twoje), community (zapis, imię, zapisani), friends (Znajomi, QR,
                         linijka „Ola idzie”), crew (czat ekipy,
                         wiersz czatu na liście, toast o nowej wiadomości), survey, layout (nagłówek, tab-bar, plakietka nieprzeczytanych, nagłówek ekranu PageHeader) — pliki kebab-case
components/ui/           prymitywy shadcn — wyłącznie przez tokeny motywu
hooks/                   use-<x>.query.ts / use-<x>.mutation.ts (jeden hook na endpoint, queryOptions):
                         me, onboarding, recommendations, events, event, event-stats, popular, attendees,
                         my-events, save-profile, save, friends, friends-going (useFriendsOn), friend-code-preview,
                         friend-invites (plakietka zaproszeń), friend-actions (invite/accept/decline/remove/regenerate),
                         crew (czat, co 3 s), send-message, my-crews (plakietki, co 30 s); use-crew-unread.ts (suma nieprzeczytanych)
lib/                     config (APP_CONFIG), auth (Cognito; Google: kod + PKCE z ../shared/oauth.ts), api (Result, błędy, ponawianie zimnego startu),
                         schemas (Zod odpowiedzi API), query-keys, search, categories, geo, wizard (walidacja ankiety),
                         events (formaty terminów/cen), explore (filtry, sortowanie), community (zapisy: stan
                         optymistyczny, podpisy), my-events (Twoje: grupy, wypisanie), crew-chat (czat ekipy: łączenie
                         odpowiedzi, komunikaty Wodzireja, podglądy, nieprzeczytane), friends (normalizeCode jak backend, inviteLink, friendsLine,
                         qrPath), login-redirect (powrót po logowaniu), onboarding-hint (ankieta wymuszana tylko bez profilu; nowe wymagane
                         pytania = baner na „Dla Ciebie”, „Później” per wersja pytań), name-prompt (prośba o imię po 409), maps (osadzona mapa
                         z trasą), nav, recommendations-cache, theme, storage, utils (cn)
styles.css               Tailwind + tokeny (jasny i ciemny) — jedyny plik CSS
public/                  ikony i manifest PWA (config.js tylko lokalnie)
```
Testy obok kodu: `lib/*.test.ts`. Import: alias `@/` = `client/`.

## Zasady
- **Nowy ekran = plik w `routes/`** (cienki), widok w `components/<obszar>/`.
- **Dane tylko przez TanStack Query:** `queryOptions` + hook w `hooks/`, klucze w `lib/query-keys.ts`, odpowiedzi przez Zod w `lib/schemas.ts`, zapytania przez `apiGet`/`apiPut`/`apiDelete` z `lib/api.ts`. Bez `fetch` w komponentach i bez `useEffect` do pobierania danych.
- **Kontrakt z backendem** (Python): ścieżki i kształty jak w docstringu `src/client_api/handler.py`, modelach Pydantic `src/client_api/schemas.py` (panel partnera: `src/api/schemas.py`), `onboarding.py`, `src/recommender_api/present.py` — Zod w `lib/schemas.ts` opisuje te same kształty. Zmiana kontraktu = Zod tu + Pydantic tam + testy obu stron w tym samym PR. Schematy Zod tolerancyjne (pola opcjonalne opcjonalne). Błędy API (jeden format): `{error: "komunikat PL", fields?, code?, requestId?}` — pokazujemy komunikat; `409` / `code: "needs_onboarding"` (albo 409 bez kodu) → `/profil`; `409 name_required` → prośba o imię; `409 friend_limit` → toast; 401 → jedno odświeżenie tokenu, potem `/login` (z `redirect` na bieżący adres).
- **Rekomendacje:** `retry: false` + pomocnik zimnego startu z `lib/api.ts` (ponowienia po 5 i 10 s, komunikat „Dobieramy propozycje…”). `202 {"status": "preparing"}` (zestaw się liczy) obsługuje `pollWhilePreparing`, a `"updating": true` — `refetchInterval` co 3 s. Parametry zapytania z filtrów: `recommendationsParams` (`lib/search.ts`); `limit` = 16 jak na serwerze (inny limit = inny zapisany zestaw). Po zapisie ankiety: `setQueryData(["me"])` i `removeQueries(["recommendations"])`.
- **Zapisy:** `useSave` (`hooks/use-save.mutation.ts`) zmienia stan i licznik optymistycznie we wszystkich cache (`events`, `popular`, `event`, `attendees`, `event-stats`, `my-events` — tu wypisanie usuwa wydarzenie), przy błędzie przywraca i pokazuje toast, po sukcesie unieważnia `attendees`, `popular`, `events`, `friends-going`, `my-events` (po wypisaniu bez ponownego pobrania: GSI `byUser` jest ostatecznie spójny) i `my-crews`, a po wypisaniu usuwa zapamiętany czat (`crew`). Karty rekomendacji dostają `saves`/`saved` z `GET /api/events/stats?ids=` (`withStats`). Jedna karta (`EventCard`) na wszystkich listach.
- **Stan w adresie:** filtry ekranu głównego i Eksploruj to search params walidowane Zodem (`lib/search.ts`, `lib/explore.ts`). Nawigacja przez `<Link>` / `navigate`.
- **Lokalizacja użytkownika** służy do liczenia odległości na kliencie i — gdy użytkownik się zgodzi — jako punkt startu trasy w osadzonej mapie Google (Maps Embed API, `lib/maps.ts`; bez zgody start z dzielnicy z profilu). **Do naszego API jej nie wysyłamy** i nie logujemy.
- **Mapa dojazdu:** iframe Maps Embed API (`components/events/route-map.tsx`) tylko z kluczem `mapsEmbedKey` z `config.js` (SSM `/codzis/google-maps-embed-key` → Terraform → `config.js`); bez klucza zostaje link do Map Google (`mapsUrl`, tryb komunikacji miejskiej).
- **Logowanie Google** (gdy `config.js` ma `googleEnabled` i `cognitoDomain`): przycisk w `AuthForm` → Hosted UI z `identity_provider=Google` (kod + PKCE, `../shared/oauth.ts`, wspólne z panelem organizatora). Powrót na stronę główną `/?code=…`: `hasSession()` (strażnik tras) najpierw wymienia kod na sesję (`googleSignInResult`), nieudany powrót trafia do formularza przez loader `/login`. Adres powrotu = strona główna z `callback_urls` w `infra/client_auth.tf` — nie zmieniaj go bez Terraforma. Wylogowanie po Google przechodzi też przez `/logout` Hosted UI.
- **Bezpieczeństwo:** bez `dangerouslySetInnerHTML`; linki zewnętrzne tylko `http(s)` z `rel="noopener noreferrer"`; tokenów nie logujemy.

## Recepty (wzorowane na firmowym `valinor`)
- **Nowe pole z API na istniejącym ekranie:** backend dodaje pole (addytywnie) → dopisz je jako opcjonalne w schemacie w `lib/schemas.ts` → użyj w komponencie; formatowanie (daty, ceny, odległości) jako czysta funkcja w `lib/` z testem.
- **Nowy endpoint:** schemat odpowiedzi w `lib/schemas.ts` → klucz w `lib/query-keys.ts` → `hooks/use-<x>.query.ts` z `queryOptions` (albo `use-<x>.mutation.ts`, a po sukcesie `setQueryData`/`invalidateQueries` zależnych kluczy) → użycie w loaderze trasy (`ensureQueryData`) i komponencie.
- **Nowy ekran:** plik w `routes/` (np. `_app/ulubione.tsx` dla zalogowanych) z `loader`, `pendingComponent`, `errorComponent`, `component`; widok w `components/<obszar>/<nazwa>-view.tsx`; link w `NAV_ITEMS` (`lib/nav.ts`: nagłówek i dolny pasek). Filtry/stan widoku jako search params z `validateSearch` (Zod z domyślnymi).
- **Nowy komponent UI:** najpierw sprawdź `components/ui/`; brakujący prymityw przez shadcn, komponent funkcji w `components/<obszar>/`.

## Wygląd (żeby nie wyglądało jak „AI slop”)
- Tylko klasy Tailwind i tokeny z `styles.css` (`bg-primary`, `text-muted-foreground`, `bg-brand`, `text-brand-ink`, `bg-poster-kultura`…). **Bez kolorów hex w komponentach, bez inline `style`, bez nowych plików CSS.**
- Kierunek „Plakat”: tekst w Familjen Grotesk (`font-sans`), nagłówki-plakaty, ceny i godziny w Anybody (`font-display` + szerokość `[font-stretch:55%…130%]`, wersaliki). Kolory kategorii na kartach i w nagłówku szczegółów z `components/events/poster-tone.ts` (kultura czerwień, sport błękit, rekreacja ochra). Ramki kart i pól: `border-2 border-input` (atrament); cienkie podziały: `border`. Ostre rogi wszędzie (`--radius` = 0), `rounded-full` tylko dla kółek-znaczników.
- Kolory przygaszone jak farba drukarska na szarym papierze (nie czyste RGB), znak wodny godziny tylko o krok ciemniejszy od pola. Nowy kolor = token w `styles.css`, nie mocniejsze nasycenie.
- Nagłówek ekranu: `components/layout/page-header.tsx` (`PageHeader`: tytuł-plakat w Anybody, wersaliki, opcjonalny napis nad nim i zdanie pod nim) — ten sam na Twoje, Znajomi, Popularne, Eksploruj i w ankiecie; ekran główny i szczegóły mają własne pole plakatu. Nowy ekran = `PageHeader`, nie własny `<h1>`.
- Statyczna `public/polityka-prywatnosci.html` ma te same kolory i formy (czerwone pole plakatu, ramki atramentem), ale bez zewnętrznych zasobów: zwężone kroje systemowe zamiast fontów Google.
- Zdjęcie na karcie (`event-card.tsx`): wysuwa się na pole plakatu po najechaniu myszą, przy fokusie, na dotyku gdy karta jest na środku ekranu albo po stuknięciu w plakat (`hooks/use-photo-reveal.ts`); bez zdjęcia karta zostaje plakatem.
- tailwind-merge usuwa `leading-*` stojące przed klasą rozmiaru tekstu w tym samym `cn(...)` – rozmiar podawaj przed `leading-*`.
- Nowy prymityw: `npx shadcn@latest add <komponent>`, potem dostosuj do tokenów (nie zostawiaj domyślnego szarego).
- Zakaz: gradienty, rozmycia/szkło, emoji w UI, ikony „magii” (✨), cienie na wszystkim (cień tylko sheet/toast), dwukolorowe logotypy, ozdobne koła w tle, angielskie teksty. Teksty po polsku.
- Jedna skala odstępów (4/8/12/16/24/32), cele dotykowe ≥ 44 px, widoczny `focus-visible`, animacje 150–250 ms z `motion-safe:`. Czerwony tekst: `text-brand-ink`.
- Mobile first (390 px), desktop od 860 px.

## Gotowe, gdy
`npm test`, `npm run typecheck` i `npm run build` przechodzą; logika w `lib/` ma testy (najpierw test); zmiana kontraktu API uzgodniona z właścicielem backendu. Commity po polsku: `feat(portal): …`, `fix(portal): …`.
