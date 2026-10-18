import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { CHAT_POLL_MS, markCrewRead, mergeCrew } from "@/lib/crew-chat";
import { crewKey, myCrewsKey } from "@/lib/query-keys";
import { type Crew, CrewSchema, type MyCrews } from "@/lib/schemas";

/**
 * GET /api/events/{id}/crew: moja ekipa i jej czat (tylko dla zapisanych - `enabled`). Pierwsze zapytanie
 * dołącza do ekipy (backend), kolejne co 3 s (tylko przy widocznej karcie) pytają o nowe wiadomości od `cursor`
 * i dokładają je do zapamiętanych (mergeCrew). Każde oznacza czat jako przeczytany, więc plakietka tej ekipy
 * spada do zera od razu (markCrewRead); po pierwszym wejściu lista ekip odświeża się w całości.
 */
export function useCrew(id: string, enabled: boolean) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: crewKey(id),
    queryFn: async ({ signal }) => {
      const prev = queryClient.getQueryData<Crew>(crewKey(id));
      const after = prev?.cursor ? `?after=${encodeURIComponent(prev.cursor)}` : "";
      const path = `/api/events/${encodeURIComponent(id)}/crew${after}`;
      const crew = mergeCrew(prev, unwrap(await apiGet(path, CrewSchema, signal)));
      if (prev) queryClient.setQueryData<MyCrews>(myCrewsKey(), (mine) => markCrewRead(mine, id, crew));
      else void queryClient.invalidateQueries({ queryKey: myCrewsKey() });
      return crew;
    },
    enabled,
    staleTime: 0,
    refetchInterval: CHAT_POLL_MS,
  });
}
