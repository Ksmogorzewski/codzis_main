import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { friendsGoingKey } from "@/lib/query-keys";
import { FriendsGoingSchema } from "@/lib/schemas";

// GET /api/friends/going: nadchodzące wydarzenia znajomych + mapa wydarzenie -> imiona. Jedno zapytanie
// na ekran: wszystkie karty czytają ten sam wpis w cache (linijka „Ola idzie”).
export const friendsGoingQueryOptions = queryOptions({
  queryKey: friendsGoingKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/friends/going", FriendsGoingSchema, signal)),
});

export const useFriendsGoing = () => useQuery(friendsGoingQueryOptions);

const NOBODY: readonly string[] = [];

/** Imiona znajomych zapisanych na wydarzenie (bez danych albo przy błędzie - pusta lista). */
export function useFriendsOn(eventId: string): readonly string[] {
  const going = useQuery({ ...friendsGoingQueryOptions, select: (d) => d.byEvent[eventId] });
  return going.data ?? NOBODY;
}
