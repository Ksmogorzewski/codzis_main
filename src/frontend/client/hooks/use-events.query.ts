import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { type EventsParams, eventsPath } from "@/lib/explore";
import { eventsKey } from "@/lib/query-keys";
import { EventListSchema } from "@/lib/schemas";

// GET /api/events?…: wszystkie wydarzenia w oknie czasu (Eksploruj), bez filtra profilu.
export const eventsQueryOptions = (p: EventsParams) =>
  queryOptions({
    queryKey: eventsKey(p),
    queryFn: async ({ signal }) => unwrap(await apiGet(eventsPath(p), EventListSchema, signal)),
  });

/** Przy zmianie filtrów zostają poprzednie karty (przygaszone), zamiast mignięcia szkieletu. */
export const useEvents = (p: EventsParams) => useQuery({ ...eventsQueryOptions(p), placeholderData: keepPreviousData });
