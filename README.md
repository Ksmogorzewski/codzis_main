# WarsawNow

## Wejdź: [portal.waw-out.pl](https://portal.waw-out.pl)

**Konto testowe dla jury:** login `w4r54wn0w@gmail.com`, hasło `1qaz@WSX`

**Warszawa ma setki darmowych wydarzeń i zajęć każdego tygodnia. WarsawNow pomaga wybrać coś dla siebie — i nie iść tam samemu.**

Hackathon Otwarte Dane Warszawa 2026, wyzwanie 3 „Warszawa: Twój ruch!”.

---

## Problem

Miasto organizuje w każdym tygodniu setki darmowych zajęć i wydarzeń: jogę w parkach, treningi w ośrodkach sportu, warsztaty w bibliotekach i domach kultury, koncerty, spacery. Informacja o nich jest rozproszona po kalendarzach dzielnic i serwisach instytucji. A nawet kiedy ktoś coś znajdzie, często nie idzie — **bo nie ma z kim**. Według CBOS co dwunasty dorosły Polak czuje się samotny bardzo często albo stale, najczęściej ludzie młodzi.

## Rozwiązanie

1. **Krótka ankieta** (kafelki: z kim, klimat, budżet, dojazd, dzielnica) buduje profil.
2. **„Dla Ciebie”** — propozycje na dziś, jutro, weekend albo 7 dni, dobrane przez AI z otwartych danych miasta, każda z uzasadnieniem („Pasuje: lubisz ruch i poranki”), z odległością i czasem dojścia.
3. **„Idę”** — zapis na wydarzenie. Widać, kto jeszcze się wybiera i ile osób idzie.
4. **Znajomi** — dodajesz ich kodem albo QR (z akceptacją). Na kartach widać „Ola i Kuba idą”, a w zakładce Znajomi — na co idą Twoi ludzie.
5. **Ekipa** — osoby zapisane na to samo wydarzenie trafiają do małej ekipy z czatem, żeby można było się umówić i odnaleźć na miejscu.
6. **Popularne** — co w najbliższym tygodniu przyciąga najwięcej osób.

## Wykorzystanie otwartych danych

| Zbiór z dane.um.warszawa.pl | Endpoint | Rekordów w bazie (18.10) | Do czego |
|---|---|---|---|
| Kalendarz wydarzeń | `get_bmm_kalendarz_wydarzen` | 618 | wydarzenia jednorazowe i wielodniowe |
| Zajęcia sportowe | `get_bmm_zajecia_sportowe` | 591 | zajęcia cykliczne (dzień tygodnia, godziny) |

Łącznie **1 241 wydarzeń i zajęć**, w **18 dzielnicach**, z czego **508 bezpłatnych** i **545 cyklicznych**.

Co robimy z danymi (a nie tylko je wyświetlamy):
- **Regularny import** z API miasta (API blokuje adresy chmury, więc importer uruchamiamy lokalnie), ujednolicenie obu zbiorów do jednego schematu (terminy, miejsce, dzielnica, współrzędne, cena, grupa docelowa), wykrywanie zmian i wygasanie zakończonych wydarzeń.
- **Tagowanie AI w 10 wymiarach** (temat, format, grupa odbiorców, koszt, pod dachem / plener, zapisy, poziom aktywności, okazja, dostępność…) z zamkniętych list — dzięki temu filtry i rekomendacje działają tak samo dla kalendarza i zajęć sportowych. Opis zajęć sportowych nie ma np. informacji „hala czy plener” — tagowanie ją uzupełnia.
- **Rekomendacje (RAG):** embeddingi wydarzeń + ranking modelem językowym z krótkim uzasadnieniem, dopasowane do profilu, okna czasu i lokalizacji.
- **Uczciwość danych:** każda karta pokazuje źródło i czas odczytu; nie dopisujemy faktów, których nie ma w danych.

## Co jest nowe

- **Społeczna warstwa na miejskiej ofercie.** Aplikacje do poznawania ludzi (np. płatne kolacje z nieznajomymi) budują własną ofertę; my łączymy ludzi wokół tego, co miasto już organizuje — za darmo, w publicznych, bezpiecznych miejscach (ośrodki sportu, biblioteki, domy kultury).
- **„Nie musisz iść sam”:** zapis → znajomi → ekipa z czatem → spotkanie na miejscu. Przy zajęciach cyklicznych ta sama ekipa może spotykać się co tydzień.
- **Rekomendacja z uzasadnieniem** zamiast kolejnej listy wydarzeń.
- **Jeden katalog** z dwóch różnych zbiorów miasta, otagowany jednym modelem.

## Potencjał wdrożeniowy

- **Dla mieszkańców:** szybka decyzja „co dziś” i powód, żeby wyjść z domu z innymi.
- **Dla miasta:** wyższa frekwencja na zajęciach, za które już płaci, oraz **sygnał popytu**, którego dziś nie ma — które zajęcia są przepełnione, które puste, w jakich dzielnicach i godzinach ludzie przyszliby, gdyby mieli z kim. Spójne z celami programów takich jak „Aktywny Senior”.
- **Gotowe do utrzymania:** chmura AWS w modelu serverless (płacimy za użycie), cała infrastruktura jako kod (Terraform), testy automatyczne, logi i obsługa błędów.

## Działa teraz

- Portal: **[portal.waw-out.pl](https://portal.waw-out.pl)** — rejestracja e-mailem albo Google, ankieta, „Dla Ciebie”, wszystkie wydarzenia z filtrami, szczegóły z mapą dojazdu komunikacją miejską, „Idę”, kto się wybiera, znajomi z kodem/QR, ekipy z czatem, Popularne, Twoje wydarzenia.
- **Dane testowe na demo:** część zapisów i znajomych na liście „Kto się wybiera” pochodzi od kont testowych (oznaczonych w bazie, usuwalnych jednym poleceniem) — żeby pokazać, jak aplikacja wygląda, gdy korzysta z niej więcej osób. Wydarzenia są prawdziwe, z danych miasta.

## Architektura

```
dane.um.warszawa.pl ──▶ importer ─────────▶ kolejka ──▶ tagowanie AI ──▶ baza wydarzeń
                                                              │
portal (React) ──▶ API (Lambda) ──▶ profile, zapisy, znajomi, ekipy (DynamoDB)
              └──▶ rekomender (Lambda: embeddingi + ranking LLM)
```

React + TypeScript (TanStack Router/Query, Tailwind, shadcn) · Python na AWS Lambda (Powertools, Pydantic) · DynamoDB · Cognito · S3 + CloudFront · ECS (import i tagowanie) · Terraform.
Architektura, zasady pisania kodu i opis modułów: [AGENTS.md](AGENTS.md).

## Jakość

- Ponad 500 testów backendu (pytest, lint, typy) i ponad 200 testów frontu (vitest, typy, build).
- Jeden format błędów i logów z identyfikatorem żądania; brak danych osobowych w logach.
- Prywatność: na listach tylko imię i inicjał nazwiska, nigdy e-mail; zapisy znajomych widoczne dopiero po zaakceptowaniu zaproszenia i tylko dla nadchodzących wydarzeń; lokalizacja liczona w przeglądarce, nie trafia na serwer.
