import type { EventsParams } from "./explore";
import type { RecommendationsParams } from "./search";

// Klucze TanStack Query w jednym miejscu (mutacje aktualizują/usuwają je po zapisie).
export const meKey = () => ["me"] as const;

export const onboardingKey = () => ["onboarding"] as const;

/** Prefiks wszystkich zapytań o rekomendacje (removeQueries po zapisie profilu). */
export const recommendationsRootKey = () => ["recommendations"] as const;

export const recommendationsKey = (p: RecommendationsParams) =>
  ["recommendations", { when: p.when, q: p.q, date: p.date ?? null }] as const;

// --- Eksploruj, Popularne, szczegóły, zapisy ---

/** Prefiks list Eksploruj (unieważniany po zapisie na wydarzenie). */
export const eventsRootKey = () => ["events"] as const;

export const eventsKey = (p: EventsParams) =>
  [
    "events",
    { when: p.when, date: p.date ?? null, cat: p.cat, district: p.district ?? null, free: p.free, indoor: p.indoor, q: p.q },
  ] as const;

export const eventKey = (id: string) => ["event", id] as const;

export const popularKey = () => ["popular"] as const;

export const attendeesKey = (id: string) => ["attendees", id] as const;

/** Prefiks liczników zapisów dla kart rekomendacji (GET /api/events/stats). */
export const eventStatsRootKey = () => ["event-stats"] as const;

export const eventStatsKey = (ids: readonly string[]) => ["event-stats", [...ids].sort().join(",")] as const;

/** Zakładka „Twoje”: moje zapisy (GET /api/me/events). */
export const myEventsKey = () => ["my-events"] as const;

// --- Czat ekipy ---

/** Prefiks czatów ekip (unieważniany po podaniu imienia - czat wymaga imienia). */
export const crewRootKey = () => ["crew"] as const;

/** GET /api/events/{id}/crew: moja ekipa i wiadomości (co 3 s, nowe dokładane po `cursor`). */
export const crewKey = (id: string) => ["crew", id] as const;

/** GET /api/me/crews: moje ekipy - plakietka nieprzeczytanych w nawigacji, wiersze czatu na „Twoje”. */
export const myCrewsKey = () => ["my-crews"] as const;

// --- Znajomi ---

/** GET /api/friends: mój kod, znajomi, zaproszenia (unieważniany po każdej akcji znajomych). */
export const friendsKey = () => ["friends"] as const;

/** Plakietka „Znajomi”: liczba zaproszeń (też GET /api/friends; pod friendsKey, więc akcje znajomych ją odświeżają). */
export const friendInvitesKey = () => ["friends", "invites"] as const;

/** GET /api/friends/going: wydarzenia znajomych i mapa wydarzenie -> imiona (linijka „Ola idzie” na kartach). */
export const friendsGoingKey = () => ["friends-going"] as const;

/** GET /api/friends/code/{code}: czyj to kod (ekran zaproszenia). */
export const friendCodeRootKey = () => ["friend-code"] as const;
export const friendCodeKey = (code: string) => ["friend-code", code] as const;
