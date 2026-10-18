import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { friendsKey } from "@/lib/query-keys";
import { FriendsOverviewSchema } from "@/lib/schemas";

// GET /api/friends: mój kod, znajomi, zaproszenia do mnie i ode mnie. 409 name_required = konto bez imienia
// (globalny onError w main.tsx pokazuje prośbę o imię).
export const friendsQueryOptions = queryOptions({
  queryKey: friendsKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/friends", FriendsOverviewSchema, signal)),
});

/** Na zakładce Znajomi co 15 s: zaproszenie od osoby, która właśnie zeskanowała mój QR, pojawia się samo. */
export const useFriends = (options: { live?: boolean } = {}) =>
  useQuery({ ...friendsQueryOptions, refetchInterval: options.live ? 15_000 : false });
