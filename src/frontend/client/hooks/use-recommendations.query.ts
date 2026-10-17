import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { apiGet, pollWhilePreparing, unwrap, withColdStartRetry, withSlowHint } from "@/lib/api";
import { recommendationsKey } from "@/lib/query-keys";
import { RecommendationsResponseSchema } from "@/lib/schemas";
import type { RecommendationsParams } from "@/lib/search";

export type { RecommendationsParams };

// API zwraca do 16 kart (pula dla LLM); na ekranie pokazujemy do 12 po filtrze kategorii (lib/categories.ts).
// = DEFAULT_LIMIT w src/recommender_api/handler.py: z tym limitem serwer liczy zestawy z góry.
export const RECOMMENDATIONS_LIMIT = 16;

// Zestaw z "updating": true (w tle liczy się nowsza wersja) - dopytujemy co tyle ms.
export const UPDATING_REFETCH_MS = 3000;

// Po tylu ms bez odpowiedzi pokazujemy komunikat zimnego startu.
export const SLOW_HINT_MS = 6000;

export function recommendationsPath({ when, q, date }: RecommendationsParams): string {
  const params = new URLSearchParams({ when });
  if (date) params.set("date", date);
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
      // 202 "preparing" (zestaw się liczy) -> pytamy ponownie; każde pytanie przeżywa też zimny start Lambdy.
      const result = await withSlowHint(
        () =>
          pollWhilePreparing(
            () =>
              withColdStartRetry(() => apiGet(recommendationsPath(p), RecommendationsResponseSchema, signal), {
                signal,
                onRetry: () => setColdStart(key, true),
              }),
            { signal },
          ),
        SLOW_HINT_MS,
        () => setColdStart(key, true),
        () => setColdStart(key, false),
      );
      return unwrap(result);
    },
    // Ponawia już withColdStartRetry (5 s, 10 s); globalny retry dodałby czwarte wywołanie.
    retry: false,
    // Wersja wektorowa już jest, AI (albo odświeżenie) liczy się w tle: dopytujemy, aż updating = false.
    refetchInterval: (query) => (query.state.data?.updating ? UPDATING_REFETCH_MS : false),
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
