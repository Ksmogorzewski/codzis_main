# Front WarsawNow (`src/frontend/`)

Jeden projekt Vite, dwie aplikacje: **portal klienta** (`client/`, tryb `client`) i **panel partnera** (`partner/`, tryb `partner`). Ten plik opisuje portal klienta. **Pilnuj struktury opisanej niżej**; jeśli zmiana jej nie pasuje, zatrzymaj się i zapytaj, zamiast tworzyć nowy wzorzec. Panelu partnera nie zmieniaj bez zgody Krzysztofa.

## Produkt (portal klienta)
Logowanie (Cognito: e-mail + hasło, rejestracja z kodem z e-maila, reset hasła) → ankieta z kroków `GET /api/onboarding` → propozycje z `GET /api/recommendations` (filtr czasu dziś/jutro/weekend/7 dni/inny dzień, wyszukiwarka, kategorie, odległość z geolokalizacji, uzasadnienie „Pasuje: …”) → szczegóły wydarzenia (z mapą Google i trasą komunikacją miejską). Wygląd: mockup WarsawNow, wariant 1a Karty.
**Poza zakresem bez zgody zespołu:** logowanie Google, „Sponsorowane”, warstwa społecznościowa, pogoda.

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
  _app/index.tsx         propozycje (search params: when, date, q, cat)
  _app/profil.tsx        ankieta
  _app/wydarzenie.$id.tsx szczegóły
components/<obszar>/     auth, events, survey, layout — pliki kebab-case
components/ui/           prymitywy shadcn — wyłącznie przez tokeny motywu
hooks/                   use-<x>.query.ts / use-<x>.mutation.ts (jeden hook na endpoint, queryOptions)
lib/                     config (APP_CONFIG), auth (Cognito), api (Result, błędy, ponawianie zimnego startu),
                         schemas (Zod odpowiedzi API), query-keys, search, categories, geo, wizard (walidacja ankiety),
                         events (formaty terminów/cen), maps (osadzona mapa z trasą), recommendations-cache, theme,
                         storage, utils (cn)
styles.css               Tailwind + tokeny (jasny i ciemny) — jedyny plik CSS
public/                  ikony i manifest PWA (config.js tylko lokalnie)
```
Testy obok kodu: `lib/*.test.ts`. Import: alias `@/` = `client/`.

## Zasady
- **Nowy ekran = plik w `routes/`** (cienki), widok w `components/<obszar>/`.
- **Dane tylko przez TanStack Query:** `queryOptions` + hook w `hooks/`, klucze w `lib/query-keys.ts`, odpowiedzi przez Zod w `lib/schemas.ts`, zapytania przez `apiGet`/`apiPut` z `lib/api.ts`. Bez `fetch` w komponentach i bez `useEffect` do pobierania danych.
- **Kontrakt z backendem** (Python): ścieżki i kształty jak w `src/client_api/handler.py`, `onboarding.py`, `src/recommender_api/present.py`. Schematy Zod tolerancyjne (pola opcjonalne opcjonalne). Błędy API: `{error: "komunikat PL", fields?, code?}` — pokazujemy komunikat; `409` / `code: "needs_onboarding"` → `/profil`; 401 → jedno odświeżenie tokenu, potem `/login`.
- **Rekomendacje:** `retry: false` + pomocnik zimnego startu z `lib/api.ts` (ponowienia po 5 i 10 s, komunikat „Dobieramy propozycje…”). `202 {"status": "preparing"}` (zestaw się liczy) obsługuje `pollWhilePreparing`, a `"updating": true` — `refetchInterval` co 3 s. Parametry zapytania z filtrów: `recommendationsParams` (`lib/search.ts`); `limit` = 16 jak na serwerze (inny limit = inny zapisany zestaw). Po zapisie ankiety: `setQueryData(["me"])` i `removeQueries(["recommendations"])`.
- **Stan w adresie:** filtry ekranu głównego to search params walidowane Zodem (`lib/search.ts`). Nawigacja przez `<Link>` / `navigate`.
- **Lokalizacja użytkownika** służy do liczenia odległości na kliencie i — gdy użytkownik się zgodzi — jako punkt startu trasy w osadzonej mapie Google (Maps Embed API, `lib/maps.ts`; bez zgody start z dzielnicy z profilu). **Do naszego API jej nie wysyłamy** i nie logujemy.
- **Mapa dojazdu:** iframe Maps Embed API (`components/events/route-map.tsx`) tylko z kluczem `mapsEmbedKey` z `config.js` (SSM `/codzis/google-maps-embed-key` → Terraform → `config.js`); bez klucza zostaje link do Map Google (`mapsUrl`, tryb komunikacji miejskiej).
- **Bezpieczeństwo:** bez `dangerouslySetInnerHTML`; linki zewnętrzne tylko `http(s)` z `rel="noopener noreferrer"`; tokenów nie logujemy.

## Recepty (wzorowane na firmowym `valinor`)
- **Nowe pole z API na istniejącym ekranie:** backend dodaje pole (addytywnie) → dopisz je jako opcjonalne w schemacie w `lib/schemas.ts` → użyj w komponencie; formatowanie (daty, ceny, odległości) jako czysta funkcja w `lib/` z testem.
- **Nowy endpoint:** schemat odpowiedzi w `lib/schemas.ts` → klucz w `lib/query-keys.ts` → `hooks/use-<x>.query.ts` z `queryOptions` (albo `use-<x>.mutation.ts`, a po sukcesie `setQueryData`/`invalidateQueries` zależnych kluczy) → użycie w loaderze trasy (`ensureQueryData`) i komponencie.
- **Nowy ekran:** plik w `routes/` (np. `_app/ulubione.tsx` dla zalogowanych) z `loader`, `pendingComponent`, `errorComponent`, `component`; widok w `components/<obszar>/<nazwa>-view.tsx`; link w `components/layout/header.tsx`. Filtry/stan widoku jako search params z `validateSearch` (Zod z domyślnymi).
- **Nowy komponent UI:** najpierw sprawdź `components/ui/`; brakujący prymityw przez shadcn, komponent funkcji w `components/<obszar>/`.

## Wygląd (żeby nie wyglądało jak „AI slop”)
- Tylko klasy Tailwind i tokeny z `styles.css` (`bg-primary`, `text-muted-foreground`, `bg-brand`, `text-brand-ink`…). **Bez kolorów hex w komponentach, bez inline `style`, bez nowych plików CSS.**
- Nowy prymityw: `npx shadcn@latest add <komponent>`, potem dostosuj do tokenów (nie zostawiaj domyślnego szarego).
- Zakaz: gradienty (poza tłem logowania z mockupu), rozmycia/szkło, emoji w UI, ikony „magii” (✨), cienie na wszystkim, angielskie teksty. Teksty po polsku, z mockupu.
- Jedna skala odstępów (4/8/12/16/24/32), cele dotykowe ≥ 44 px, widoczny `focus-visible`, animacje 150–250 ms z `motion-safe:`. Czerwony tekst: `text-brand-ink`.
- Mobile first (390 px), desktop od 860 px.

## Gotowe, gdy
`npm test`, `npm run typecheck` i `npm run build` przechodzą; logika w `lib/` ma testy (najpierw test); zmiana kontraktu API uzgodniona z właścicielem backendu. Commity po polsku: `feat(portal): …`, `fix(portal): …`.
