import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { eventsRootKey, eventKey, popularKey, recommendationsRootKey } from "@/lib/query-keys";
import { type Card, type EventDetail, EventDetailSchema } from "@/lib/schemas";

// GET /api/events/{id}: karta + pełny opis (bez HTML), terminy, czas importu, zapisy. 404 = brak wydarzenia.
export const eventQueryOptions = (id: string) =>
  queryOptions({
    queryKey: eventKey(id),
    queryFn: async ({ signal }) =>
      unwrap(await apiGet(`/api/events/${encodeURIComponent(id)}`, EventDetailSchema, signal)),
  });

/**
 * Szczegóły; zanim przyjdą, pokazujemy kartę z listy, z której przyszedł użytkownik (Eksploruj,
 * Popularne, rekomendacje) - bez pełnego opisu, który dochodzi po chwili.
 */
export function useEvent(id: string) {
  const queryClient = useQueryClient();
  return useQuery({
    ...eventQueryOptions(id),
    placeholderData: (): EventDetail | undefined => {
      for (const queryKey of [eventsRootKey(), popularKey(), recommendationsRootKey()]) {
        for (const [, data] of queryClient.getQueriesData<{ items?: Card[] }>({ queryKey })) {
          const card = data?.items?.find((c) => c.id === id);
          if (card) return { ...card, text: "", occurrences: [], importedAt: null };
        }
      }
      return undefined;
    },
  });
}
