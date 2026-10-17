import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { eventKey } from "@/lib/query-keys";
import { EventDetailSchema } from "@/lib/schemas";

// GET /api/events/{id}: karta + pełny opis (bez HTML), terminy, czas importu, zapisy. 404 = brak wydarzenia.
export const eventQueryOptions = (id: string) =>
  queryOptions({
    queryKey: eventKey(id),
    queryFn: async ({ signal }) =>
      unwrap(await apiGet(`/api/events/${encodeURIComponent(id)}`, EventDetailSchema, signal)),
  });

export const useEvent = (id: string) => useQuery(eventQueryOptions(id));
