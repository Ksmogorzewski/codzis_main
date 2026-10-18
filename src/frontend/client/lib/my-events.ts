// Zakładka „Twoje” (GET /api/me/events): podział na nadchodzące i minione, zmiana listy po zapisie / wypisaniu.
// Kolejność ustala serwer (nadchodzące od najbliższego terminu, minione od najświeższego).
import type { KnownSaveState, SaveState } from "./community";
import { dayLabel, warsawDate } from "./events";
import type { MyEvent, MyEvents, Slot } from "./schemas";

export function groupMyEvents(items: readonly MyEvent[]): { upcoming: MyEvent[]; past: MyEvent[] } {
  return { upcoming: items.filter((c) => !c.past), past: items.filter((c) => c.past) };
}

/**
 * Lista po zmianie stanu zapisu jednego wydarzenia: wypisanie usuwa je od razu (optymistycznie),
 * zapis zmienia licznik. Nowo zapisanego nie dodajemy - nie mamy jego karty; dociąga je odświeżenie listy.
 */
export function patchMyEvents(list: MyEvents, id: string, next: (s: SaveState) => KnownSaveState): MyEvents {
  return {
    ...list,
    items: list.items.flatMap((item) => {
      if (item.id !== id) return [item];
      const state = next(item);
      return state.saved ? [{ ...item, ...state }] : [];
    }),
  };
}

/** Termin minionego wydarzenia (slot = ostatni termin z API): „Zakończone · Wt 13.10”; bez daty „Termin minął”. */
export function pastSlotLabel(slot: Slot | null, now: Date): string {
  if (!slot || slot.recurring) return "Termin minął";
  const day = dayLabel(warsawDate(new Date(slot.end ?? slot.start)), now);
  return `Zakończone · ${day.charAt(0).toUpperCase()}${day.slice(1)}`;
}
