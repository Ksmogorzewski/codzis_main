import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { eventStatsKey } from "@/lib/query-keys";
import { EventStatsSchema } from "@/lib/schemas";

/** Tyle id przyjmuje serwer w jednym zapytaniu (BatchGetItem). */
export const MAX_STATS_IDS = 100;

// GET /api/events/stats?ids=…: liczniki zapisów i „czy ja” dla kart rekomendacji (one ich nie mają).
export const eventStatsQueryOptions = (ids: readonly string[]) =>
  queryOptions({
    queryKey: eventStatsKey(ids),
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({ ids: [...ids].sort().slice(0, MAX_STATS_IDS).join(",") });
      return unwrap(await apiGet(`/api/events/stats?${params}`, EventStatsSchema, signal));
    },
  });

/** Bez kart nie pytamy. Błąd = karty bez licznika (zapis nadal działa). */
export const useEventStats = (ids: readonly string[]) =>
  useQuery({ ...eventStatsQueryOptions(ids), enabled: ids.length > 0, retry: false });
