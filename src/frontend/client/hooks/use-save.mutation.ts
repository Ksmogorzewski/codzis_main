import { type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorText } from "@/components/layout/route-error";
import { ApiRequestError, apiDelete, apiPut, unwrap } from "@/lib/api";
import { currentDisplayName } from "@/lib/auth";
import {
  type KnownSaveState,
  patchAttendees,
  patchSaveInList,
  type SaveState,
  savedAsText,
  type StatsMap,
  toggleSave,
} from "@/lib/community";
import { patchMyEvents } from "@/lib/my-events";
import {
  attendeesKey,
  eventKey,
  eventStatsRootKey,
  eventsRootKey,
  friendsGoingKey,
  myEventsKey,
  popularKey,
} from "@/lib/query-keys";
import {
  type Attendees,
  type EventDetail,
  type EventList,
  type FriendsGoing,
  type MyEvents,
  SaveResultSchema,
} from "@/lib/schemas";

export type SaveVars = { id: string; save: boolean };

// Wszystkie miejsca w cache, gdzie widać stan zapisu danego wydarzenia.
const keysFor = (id: string) => [
  eventsRootKey(),
  popularKey(),
  eventKey(id),
  attendeesKey(id),
  eventStatsRootKey(),
  myEventsKey(),
  friendsGoingKey(),
];

/**
 * Ustawia stan zapisu wydarzenia we wszystkich listach, szczegółach, liście zapisanych i licznikach;
 * na liście „Twoje” wypisanie od razu usuwa wydarzenie.
 */
function patchCaches(qc: QueryClient, id: string, next: (s: SaveState) => KnownSaveState) {
  const patchList = (list: EventList | undefined) => list && { ...list, items: patchSaveInList(list.items, id, next) };
  qc.setQueriesData<EventList>({ queryKey: eventsRootKey() }, patchList);
  qc.setQueriesData<EventList>({ queryKey: popularKey() }, patchList);
  qc.setQueryData<FriendsGoing>(friendsGoingKey(), (g) => g && { ...g, items: patchSaveInList(g.items, id, next) });
  qc.setQueryData<EventDetail>(eventKey(id), (d) => d && { ...d, ...next(d) });
  qc.setQueryData<MyEvents>(myEventsKey(), (list) => list && patchMyEvents(list, id, next));
  qc.setQueryData<Attendees>(attendeesKey(id), (a) => a && patchAttendees(a, next(a), currentDisplayName()));
  qc.setQueriesData<StatsMap>({ queryKey: eventStatsRootKey() }, (m) => {
    const s = m?.[id];
    return m && s ? { ...m, [id]: next(s) } : m;
  });
}

/**
 * PUT / DELETE /api/events/{id}/save -> {saved, saves}. Optymistycznie: stan i licznik zmieniają się
 * od razu wszędzie (na liście zapisanych mój wpis z imieniem z ID tokenu); błąd przywraca poprzedni
 * stan i pokazuje toast. Po sukcesie: wartości z serwera, toast „Zapisano jako <imię>” i odświeżenie
 * listy zapisanych, Popularnych, list Eksploruj, „Znajomi idą” i „Twoich” (po wypisaniu tylko oznaczenie
 * jako nieaktualne: indeks byUser jest odczytem ostatecznie spójnym, a lista już jest poprawna).
 */
export function useSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, save }: SaveVars) => {
      const path = `/api/events/${encodeURIComponent(id)}/save`;
      const call = () => (save ? apiPut(path, undefined, SaveResultSchema) : apiDelete(path, SaveResultSchema));
      let r = await call();
      // 409 = rzadki konflikt transakcji: jedno ponowienie (zapis jest idempotentny). Gdyby nadal był,
      // nie oddajemy 409 dalej - globalny onError (main.tsx) uznałby go za „uzupełnij profil”.
      if (r.error?.status === 409) r = await call();
      if (r.error?.status === 409) throw new ApiRequestError({ ...r.error, status: 503, code: "save_conflict" });
      return unwrap(r);
    },
    onMutate: async ({ id, save }) => {
      const keys = keysFor(id);
      await Promise.all(keys.map((queryKey) => qc.cancelQueries({ queryKey })));
      const snapshot = keys.flatMap((queryKey) => qc.getQueriesData({ queryKey }));
      patchCaches(qc, id, (s) => toggleSave(s, save));
      return { snapshot };
    },
    onError: (error, _vars, context) => {
      for (const [key, data] of context?.snapshot ?? []) qc.setQueryData(key, data);
      toast.error(errorText(error, "Nie udało się zapisać. Spróbuj ponownie."));
    },
    onSuccess: (result, { id, save }) => {
      patchCaches(qc, id, () => result);
      if (save) toast(savedAsText(currentDisplayName()));
      void qc.invalidateQueries({ queryKey: attendeesKey(id) });
      void qc.invalidateQueries({ queryKey: popularKey() });
      void qc.invalidateQueries({ queryKey: eventsRootKey() });
      void qc.invalidateQueries({ queryKey: friendsGoingKey() });
      void qc.invalidateQueries({ queryKey: myEventsKey(), refetchType: save ? "active" : "none" });
    },
  });
}
