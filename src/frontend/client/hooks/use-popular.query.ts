import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { popularKey } from "@/lib/query-keys";
import { EventListSchema } from "@/lib/schemas";

// GET /api/popular: wydarzenia z bieżącego tygodnia (pon–nd) po liczbie zapisanych, malejąco (maks. 20).
export const popularQueryOptions = queryOptions({
  queryKey: popularKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/popular", EventListSchema, signal)),
});

export const usePopular = () => useQuery(popularQueryOptions);
