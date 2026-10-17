import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { meKey } from "@/lib/query-keys";
import { MeSchema } from "@/lib/schemas";

// GET /api/me: profil zalogowanego (backend przy okazji zapisuje ostatnie logowanie).
export const meQueryOptions = queryOptions({
  queryKey: meKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/me", MeSchema, signal)),
});

export const useMe = () => useQuery(meQueryOptions);
