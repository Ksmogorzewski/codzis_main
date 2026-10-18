# Front WarsawNow (`src/frontend/`)

Jeden projekt Vite, dwie aplikacje: **portal klienta** (`client/`, tryb `client`) i **panel partnera** (`partner/`, tryb `partner`). Ten plik opisuje portal klienta. **Pilnuj struktury opisanej niżej**; jeśli zmiana jej nie pasuje, zatrzymaj się i zapytaj, zamiast tworzyć nowy wzorzec. Panelu partnera nie zmieniaj bez zgody Krzysztofa.

## Produkt (portal klienta)
Logowanie (Cognito: e-mail + hasło, rejestracja z kodem z e-maila, reset hasła; albo „Kontynuuj z Google” przez Hosted UI) → ankieta z kroków `GET /api/onboarding` → propozycje z `GET /api/recommendations` (filtr czasu dziś/jutro/weekend/7 dni/inny dzień, wyszukiwarka, kategorie, odległość z geolokalizacji, uzasadnienie „Pasuje: …”) → szczegóły wydarzenia (`GET /api/events/{id}`: pełny opis, lista zapisanych, mapa Google z trasą komunikacją miejską). **Eksploruj** (`GET /api/events`: wszystko w oknie czasu, bez profilu), **Popularne w najbliższym tygodniu** (`GET /api/popular`, dziś + 6 dni), **Zapisz / Zapisano** na kartach i w szczegółach. Nawigacja: Dla Ciebie / Eksploruj / Popularne / Profil (nagłówek na desktopie, dolny pasek na telefonie). Wygląd: mockup WarsawNow, wariant 1a Karty.
**Imię:** wymagane przy rejestracji (atrybut Cognito `name`; walidacja `NameSchema` w `lib/auth-form.ts`: litery, spacje, myślnik, maks. 40), potem niezmienne; konta bez imienia dostają jednorazową prośbę przed pierwszym zapisem (`setMissingName` w `lib/auth.ts`). Na listach zapisanych tylko imię (brak → „Ktoś”; backend bierze imię z tokenu, a bez niego `displayName` z `codzis-users`), nigdy e-mail. Po zapisie mój wpis „<Imię> (Ty)” pojawia się od razu (imię z ID tokenu), toast „Zapisano jako <Imię>”.
**Czat ekipy (DEMO, Kacper):** w szczegółach pod „Kto się wybiera” sekcja „Ekipa na to wydarzenie” (`components/crew/crew-entry.tsx`): zapisani widzą „Wejdź na czat”, pozostali „Zapisz się, żeby dołączyć do czatu ekipy” (ten sam `useSave`). Czat: `#/wydarzenie/<id>/ekipa` (`routes/_app/wydarzenie.$id_.ekipa.tsx` → `components/crew/crew-chat-screen.tsx`; na telefonie pełny ekran nad paskiem zakładek, na desktopie karta) — lodołamacz, „X pisze…”, Wodzirej AI z punktem zbiórki z danych wydarzenia, „Pokaż Kartę Koloru” → „JESTEM TUTAJ”. **Backendu czatu nie ma:** wiadomości to scenariusz z `lib/crew-demo.ts` (znacznik `DEMO`), w UI zawsze notka „Podgląd czatu (demo)” (`demo-note.tsx`). Prawdziwe są tylko imiona zapisanych (`useAttendees`, brakujące miejsca uzupełnia demo) i moje imię z ID tokenu (`currentName`). Logika (reducer, harmonogram odpowiedzi, skład ekipy) w `lib/crew-chat.ts` z testami.
**Poza zakresem bez zgody zespołu:** „Sponsorowane”, prawdziwy backend czatu, pogoda.

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
  _app.tsx               strażnik sesji (beforeLoad)
  _app/index.tsx         Dla Ciebie: propozycje (search params: when, date, q, cat)
  _app/eksploruj.tsx     Eksploruj (search params: when, date, cat, district, free, indoor, q — lib/explore.ts)
  _app/popularne.tsx     Popularne w najbliższym tygodniu
  _app/profil.tsx        ankieta
  _app/wydarzenie.$id.tsx szczegóły (+ lista zapisanych)
  _app/wydarzenie.$id_.ekipa.tsx czat ekipy (DEMO, tylko dla zapisanych)
components/<obszar>/     auth, events, explore, popular, community (zapis, imię, zapisani), crew (czat ekipy, DEMO), survey, layout (nagłówek, tab-bar) — pliki kebab-case
components/ui/           prymitywy shadcn — wyłącznie przez tokeny motywu
hooks/                   use-<x>.query.ts / use-<x>.mutation.ts (jeden hook na endpoint, queryOptions):
                         me, onboarding, recommendations, events, event, event-stats, popular, attendees,
                         save-profile, save
lib/                     config (APP_CONFIG), auth (Cognito; Google: kod + PKCE z ../shared/oauth.ts), api (Result, błędy, ponawianie zimnego startu),
                         schemas (Zod odpowiedzi API), query-keys, search, categories, geo, wizard (walidacja ankiety),
                         events (formaty terminów/cen), explore (filtry, sortowanie), community (zapisy: stan
                         optymistyczny, podpisy), crew-chat + crew-demo (czat ekipy, DEMO), maps (osadzona mapa
                         z trasą), nav, recommendations-cache, theme, storage, utils (cn)
styles.css               Tailwind + tokeny (jasny i ciemny) — jedyny plik CSS
public/                  ikony i manifest PWA (config.js tylko lokalnie)
```
Testy obok kodu: `lib/*.test.ts`. Import: alias `@/` = `client/`.

## Zasady
- **Nowy ekran = plik w `routes/`** (cienki), widok w `components/<obszar>/`.
- **Dane tylko przez TanStack Query:** `queryOptions` + hook w `hooks/`, klucze w `lib/query-keys.ts`, odpowiedzi przez Zod w `lib/schemas.ts`, zapytania przez `apiGet`/`apiPut`/`apiDelete` z `lib/api.ts`. Bez `fetch` w komponentach i bez `useEffect` do pobierania danych.
- **Kontrakt z backendem** (Python): ścieżki i kształty jak w `src/client_api/handler.py`, `onboarding.py`, `src/recommender_api/present.py`. Schematy Zod tolerancyjne (pola opcjonalne opcjonalne). Błędy API: `{error: "komunikat PL", fields?, code?}` — pokazujemy komunikat; `409` / `code: "needs_onboarding"` → `/profil`; 401 → jedno odświeżenie tokenu, potem `/login`.
- **Rekomendacje:** `retry: false` + pomocnik zimnego startu z `lib/api.ts` (ponowienia po 5 i 10 s, komunikat „Dobieramy propozycje…”). `202 {"status": "preparing"}` (zestaw się liczy) obsługuje `pollWhilePreparing`, a `"updating": true` — `refetchInterval` co 3 s. Parametry zapytania z filtrów: `recommendationsParams` (`lib/search.ts`); `limit` = 16 jak na serwerze (inny limit = inny zapisany zestaw). Po zapisie ankiety: `setQueryData(["me"])` i `removeQueries(["recommendations"])`.
- **Zapisy:** `useSave` (`hooks/use-save.mutation.ts`) zmienia stan i licznik optymistycznie we wszystkich cache (`events`, `popular`, `event`, `attendees`, `event-stats`), przy błędzie przywraca i pokazuje toast, po sukcesie unieważnia `attendees`, `popular`, `events`. Karty rekomendacji dostają `saves`/`saved` z `GET /api/events/stats?ids=` (`withStats`). Jedna karta (`EventCard`) na wszystkich listach.
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
- Tylko klasy Tailwind i tokeny z `styles.css` (`bg-primary`, `text-muted-foreground`, `bg-brand`, `text-brand-ink`…). **Bez kolorów hex w komponentach, bez inline `style`, bez nowych plików CSS.**
- Nowy prymityw: `npx shadcn@latest add <komponent>`, potem dostosuj do tokenów (nie zostawiaj domyślnego szarego).
- Zakaz: gradienty (poza tłem logowania z mockupu), rozmycia/szkło, emoji w UI, ikony „magii” (✨), cienie na wszystkim, angielskie teksty. Teksty po polsku, z mockupu.
- Jedna skala odstępów (4/8/12/16/24/32), cele dotykowe ≥ 44 px, widoczny `focus-visible`, animacje 150–250 ms z `motion-safe:`. Czerwony tekst: `text-brand-ink`.
- Mobile first (390 px), desktop od 860 px.

## Gotowe, gdy
`npm test`, `npm run typecheck` i `npm run build` przechodzą; logika w `lib/` ma testy (najpierw test); zmiana kontraktu API uzgodniona z właścicielem backendu. Commity po polsku: `feat(portal): …`, `fix(portal): …`.
