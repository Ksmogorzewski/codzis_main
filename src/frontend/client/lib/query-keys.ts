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
