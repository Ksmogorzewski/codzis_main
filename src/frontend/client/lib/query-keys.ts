import type { RecommendationsParams } from "./search";

// Klucze TanStack Query w jednym miejscu (mutacje aktualizują/usuwają je po zapisie).
export const meKey = () => ["me"] as const;

export const onboardingKey = () => ["onboarding"] as const;

/** Prefiks wszystkich zapytań o rekomendacje (removeQueries po zapisie profilu). */
export const recommendationsRootKey = () => ["recommendations"] as const;

export const recommendationsKey = (p: RecommendationsParams) =>
  ["recommendations", { when: p.when, q: p.q, date: p.date ?? null }] as const;
