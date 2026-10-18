import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { pendingInvites } from "@/lib/friends";
import { friendInvitesKey } from "@/lib/query-keys";
import { FriendsOverviewSchema } from "@/lib/schemas";

// Plakietka „Znajomi” w nagłówku i dolnym pasku: liczba zaproszeń do mnie (incoming z GET /api/friends).
// Osobny klucz niż ekran Znajomi: konto bez imienia (409 name_required) dostaje tu 0 bez błędu, więc globalny
// onError nie otwiera prośby o imię na każdym ekranie.
export const friendInvitesQueryOptions = queryOptions({
  queryKey: friendInvitesKey(),
  queryFn: async ({ signal }) =>
    unwrap(pendingInvites(await apiGet("/api/friends", FriendsOverviewSchema, signal))),
});

/** Na każdym ekranie po zalogowaniu: co 30 s i po powrocie do karty; bez danych albo przy błędzie - 0. */
export function useFriendInvitesCount(): number {
  const invites = useQuery({ ...friendInvitesQueryOptions, refetchInterval: 30_000, refetchOnWindowFocus: true });
  return invites.data ?? 0;
}
