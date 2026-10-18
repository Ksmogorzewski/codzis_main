import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { CREWS_POLL_MS } from "@/lib/crew-chat";
import { myCrewsKey } from "@/lib/query-keys";
import { MyCrewsSchema } from "@/lib/schemas";

// GET /api/me/crews: moje ekipy (wydarzenia, na których czat już wszedłem) z nieprzeczytanymi i ostatnią wiadomością.
export const myCrewsQueryOptions = queryOptions({
  queryKey: myCrewsKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/me/crews", MyCrewsSchema, signal)),
});

/** Na każdym ekranie po zalogowaniu (plakietka „Twoje”, wiersze czatu, toast): co 30 s i po powrocie do karty. */
export function useMyCrews() {
  return useQuery({ ...myCrewsQueryOptions, refetchInterval: CREWS_POLL_MS, refetchOnWindowFocus: true });
}
