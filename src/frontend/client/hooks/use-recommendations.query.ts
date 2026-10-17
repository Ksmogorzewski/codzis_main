import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { apiGet, unwrap, withColdStartRetry } from "@/lib/api";
import { recommendationsKey } from "@/lib/query-keys";
import { RecommendationsSchema, type When } from "@/lib/schemas";

export type RecommendationsParams = { when: When; q: string };

// API zwraca do 24 kart; na ekranie pokazujemy 12 po filtrze kategorii (lib/categories.ts).
export const RECOMMENDATIONS_LIMIT = 24;

export function recommendationsPath({ when, q }: RecommendationsParams): string {
  const params = new URLSearchParams({ when });
  if (q) params.set("q", q);
  params.set("limit", String(RECOMMENDATIONS_LIMIT));
  return `/api/recommendations?${params}`;
}

// Zimny start Lambdy: które zapytania właśnie czekają na ponowienie (komunikat „Dobieramy propozycje…”).
const coldStart = new Set<string>();
const listeners = new Set<() => void>();
const hashKey = (p: RecommendationsParams) => JSON.stringify(recommendationsKey(p));

function setColdStart(key: string, on: boolean) {
  if (on === coldStart.has(key)) return;
  if (on) coldStart.add(key);
  else coldStart.delete(key);
  for (const l of listeners) l();
}

export const recommendationsQueryOptions = (p: RecommendationsParams) =>
  queryOptions({
    queryKey: recommendationsKey(p),
    queryFn: async ({ signal }) => {
      const key = hashKey(p);
      try {
        const result = await withColdStartRetry(() => apiGet(recommendationsPath(p), RecommendationsSchema), {
          signal,
          onRetry: () => setColdStart(key, true),
        });
        return unwrap(result);
      } finally {
        setColdStart(key, false);
      }
    },
    // Ponawia już withColdStartRetry (5 s, 10 s); globalny retry dodałby czwarte wywołanie.
    retry: false,
  });

/** Przy zmianie filtrów zostają poprzednie karty (przygaszone), zamiast mignięcia szkieletu. */
export const useRecommendations = (p: RecommendationsParams) =>
  useQuery({ ...recommendationsQueryOptions(p), placeholderData: keepPreviousData });

/** true, gdy zapytanie o te parametry czeka na rozgrzanie Lambdy (pierwsze wywołanie dało 0/502/503/504). */
export function useColdStart(p: RecommendationsParams): boolean {
  const key = hashKey(p);
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    () => coldStart.has(key),
    () => false,
  );
}
