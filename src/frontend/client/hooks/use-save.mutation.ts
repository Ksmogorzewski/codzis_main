import { type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorText } from "@/components/layout/route-error";
import { apiDelete, apiPut, unwrap } from "@/lib/api";
import { currentName } from "@/lib/auth";
import {
  type KnownSaveState,
  patchAttendees,
  patchSaveInList,
  type SaveState,
  type StatsMap,
  toggleSave,
} from "@/lib/community";
import { attendeesKey, eventKey, eventStatsRootKey, eventsRootKey, popularKey } from "@/lib/query-keys";
import { type Attendees, type EventDetail, type EventList, SaveResultSchema } from "@/lib/schemas";

export type SaveVars = { id: string; save: boolean };

// Wszystkie miejsca w cache, gdzie widać stan zapisu danego wydarzenia.
const keysFor = (id: string) => [eventsRootKey(), popularKey(), eventKey(id), attendeesKey(id), eventStatsRootKey()];

/** Ustawia stan zapisu wydarzenia we wszystkich listach, szczegółach, liście zapisanych i licznikach. */
function patchCaches(qc: QueryClient, id: string, next: (s: SaveState) => KnownSaveState) {
  const patchList = (list: EventList | undefined) => list && { ...list, items: patchSaveInList(list.items, id, next) };
  qc.setQueriesData<EventList>({ queryKey: eventsRootKey() }, patchList);
  qc.setQueriesData<EventList>({ queryKey: popularKey() }, patchList);
  qc.setQueryData<EventDetail>(eventKey(id), (d) => d && { ...d, ...next(d) });
  qc.setQueryData<Attendees>(attendeesKey(id), (a) => a && patchAttendees(a, next(a), currentName()));
  qc.setQueriesData<StatsMap>({ queryKey: eventStatsRootKey() }, (m) => {
    const s = m?.[id];
    return m && s ? { ...m, [id]: next(s) } : m;
  });
}

/**
 * PUT / DELETE /api/events/{id}/save -> {saved, saves}. Optymistycznie: stan i licznik zmieniają się
 * od razu wszędzie; błąd przywraca poprzedni stan i pokazuje toast. Po sukcesie: wartości z serwera
 * i odświeżenie listy zapisanych, Popularnych i list Eksploruj.
 */
export function useSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, save }: SaveVars) => {
      const path = `/api/events/${encodeURIComponent(id)}/save`;
      return unwrap(await (save ? apiPut(path, undefined, SaveResultSchema) : apiDelete(path, SaveResultSchema)));
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
    onSuccess: (result, { id }) => {
      patchCaches(qc, id, () => result);
      void qc.invalidateQueries({ queryKey: attendeesKey(id) });
      void qc.invalidateQueries({ queryKey: popularKey() });
      void qc.invalidateQueries({ queryKey: eventsRootKey() });
    },
  });
}
