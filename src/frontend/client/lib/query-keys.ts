import type { When } from "./schemas";

// Klucze TanStack Query w jednym miejscu (mutacje aktualizują/usuwają je po zapisie).
export const meKey = () => ["me"] as const;

export const onboardingKey = () => ["onboarding"] as const;

/** Prefiks wszystkich zapytań o rekomendacje (removeQueries po zapisie profilu). */
export const recommendationsRootKey = () => ["recommendations"] as const;

export const recommendationsKey = (p: { when: When; q: string }) => ["recommendations", { when: p.when, q: p.q }] as const;
