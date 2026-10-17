import { useQuery, useQueryClient } from "@tanstack/react-query";
import { recommendationsRootKey } from "@/lib/query-keys";
import { findCard } from "@/lib/recommendations-cache";
import type { Recommendations } from "@/lib/schemas";
import { lastSearch, recommendationsParams } from "@/lib/search";
import { recommendationsQueryOptions, useColdStart } from "./use-recommendations.query";

/**
 * Karta do szczegółów: najpierw z cache rekomendacji (przejście z listy), a po odświeżeniu strony
 * pobieramy listę jeszcze raz – z ostatnimi filtrami (sessionStorage) albo domyślnymi – i szukamy po id.
 */
export function useEventCard(id: string) {
  const queryClient = useQueryClient();
  const cachedResults = queryClient
    .getQueriesData<Recommendations>({ queryKey: recommendationsRootKey() })
    .map(([, data]) => data);
  const cached = findCard(cachedResults, id);

  const params = recommendationsParams(lastSearch());
  const fallback = useQuery({ ...recommendationsQueryOptions(params), enabled: cached === null });
  const coldStart = useColdStart(params);

  const found = cached ?? (fallback.data ? findCard([fallback.data], id) : null);
  return {
    found,
    isPending: found === null && fallback.isPending,
    error: found === null ? fallback.error : null,
    refetch: fallback.refetch,
    coldStart,
  };
}
