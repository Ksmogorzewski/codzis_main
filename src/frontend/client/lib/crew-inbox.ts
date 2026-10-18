// Nieprzeczytane wiadomości w czatach ekip: zakładka „Twoje”, plakietki w nawigacji, toast o nowej wiadomości.
//
// DEMO: czat nie ma backendu. Rozmowa wydarzenia to scenariusz z lib/crew-demo.ts (demoInbox: stały dla id,
// różne wydarzenia trochę się różnią), a stan „ile przeczytałem” i „ile przyszło później” trzymamy lokalnie
// (localStorage; bez niego tylko w pamięci karty przeglądarki). Nowo zapisane wydarzenie ma więc od razu
// nieprzeczytaną rozmowę startową ekipy; wejście na czat oznacza wszystko jako przeczytane. Na zakładce
// „Twoje” raz na sesję strony „przychodzi” nowa wiadomość (scheduleDemoArrival).
// Docelowo (prawdziwe API czatu, np. GET /api/me/chats -> {eventId, count, lastMessage, lastReadAt}):
// messageCount bierze liczbę z API, `read` idzie na serwer, scheduleDemoArrival znika.
import { useSyncExternalStore } from "react";
import { z } from "zod";
import { plural } from "../../shared/format";
import { DEMO_LATE_MAX, demoInbox } from "./crew-demo";
import { readJson, writeJson } from "./storage";

/** Stan czatu jednego wydarzenia: ile wiadomości przeczytałem i ile „przyszło” później (DEMO). */
export type InboxEntry = { read: number; arrived: number };
export type Inbox = Record<string, InboxEntry>;

const count = z.number().int().nonnegative();
const InboxSchema = z.record(z.string(), z.object({ read: count, arrived: count }));

const arrivedOf = (inbox: Inbox, id: string) => inbox[id]?.arrived ?? 0;

/** Liczba wiadomości w czacie wydarzenia (rozmowa startowa + te, które przyszły później). */
export const messageCount = (inbox: Inbox, id: string): number => demoInbox([], id, arrivedOf(inbox, id)).length;

export const unreadCount = (inbox: Inbox, id: string): number =>
  Math.max(0, messageCount(inbox, id) - (inbox[id]?.read ?? 0));

export const totalUnread = (inbox: Inbox, ids: readonly string[]): number =>
  ids.reduce((sum, id) => sum + unreadCount(inbox, id), 0);

/** Wszystko przeczytane; bez zmian = ten sam obiekt. */
export function markRead(inbox: Inbox, id: string): Inbox {
  const read = messageCount(inbox, id);
  if (inbox[id]?.read === read) return inbox;
  return { ...inbox, [id]: { read, arrived: arrivedOf(inbox, id) } };
}

/** DEMO: jedna nowa wiadomość w czacie; null = scenariusz się skończył. */
export function withArrival(inbox: Inbox, id: string): Inbox | null {
  const arrived = arrivedOf(inbox, id);
  if (arrived >= DEMO_LATE_MAX) return null;
  return { ...inbox, [id]: { read: inbox[id]?.read ?? 0, arrived: arrived + 1 } };
}

/** DEMO: gdzie „przyjdzie” wiadomość - pierwsze wydarzenie z listy, w którym scenariusz trwa. */
export const arrivalTarget = (inbox: Inbox, ids: readonly string[]): string | null =>
  ids.find((id) => arrivedOf(inbox, id) < DEMO_LATE_MAX) ?? null;

/** „1 nowa wiadomość”, „3 nowe wiadomości”, „5 nowych wiadomości”. */
export const unreadLabel = (n: number) => plural(n, "nowa wiadomość", "nowe wiadomości", "nowych wiadomości");

// --------------------------------------------------------------------------- magazyn

export type InboxStorage = { read: () => unknown; write: (inbox: Inbox) => void };

/** Stan w pamięci + zapis do storage (błędy storage nie psują działania w bieżącej karcie). */
export function createInboxStore(storage: InboxStorage) {
  let state: Inbox | null = null;
  let demoArrivalDone = false;
  const listeners = new Set<() => void>();

  const get = (): Inbox => {
    if (state === null) {
      let raw: unknown = null;
      try {
        raw = storage.read();
      } catch {
        raw = null;
      }
      const parsed = InboxSchema.safeParse(raw ?? {});
      state = parsed.success ? parsed.data : {};
    }
    return state;
  };

  const set = (next: Inbox) => {
    if (next === state) return;
    state = next;
    try {
      storage.write(next);
    } catch {
      // bez storage stan zostaje w pamięci do przeładowania strony
    }
    for (const l of listeners) l();
  };

  return {
    get,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    markRead: (id: string) => set(markRead(get(), id)),
    /** DEMO: nowa wiadomość w czacie; false = nic nie przyszło. */
    arrive(id: string): boolean {
      const next = withArrival(get(), id);
      if (next) set(next);
      return next !== null;
    },
    /** DEMO: symulacja nowej wiadomości tylko raz na sesję strony. */
    claimDemoArrival(): boolean {
      if (demoArrivalDone) return false;
      demoArrivalDone = true;
      return true;
    },
  };
}

export type InboxStore = ReturnType<typeof createInboxStore>;

const STORAGE_KEY = "warsawnow.crew-inbox.v1";

export const inboxStore = createInboxStore({
  read: () => readJson<unknown>("local", STORAGE_KEY),
  write: (inbox) => writeJson("local", STORAGE_KEY, inbox),
});

/** Aktualny stan przeczytanych (odświeża komponent po każdej zmianie). */
export const useInbox = (): Inbox => useSyncExternalStore(inboxStore.subscribe, inboxStore.get);

// --------------------------------------------------------------------------- DEMO: nowa wiadomość

/** Po tylu ms od wejścia na „Twoje” przychodzi symulowana wiadomość (raz na sesję strony). */
export const DEMO_ARRIVAL_MS = 25_000;

/**
 * DEMO: po `delayMs` w czacie pierwszego wydarzenia z `ids` (najbliższe nadchodzące), w którym scenariusz
 * jeszcze trwa, „przychodzi” nowa wiadomość; `onArrive(id)` pokazuje toast. Raz na sesję strony.
 * Zwraca funkcję anulującą (wyjście z ekranu przed czasem = nic się nie dzieje).
 */
export function scheduleDemoArrival(
  store: InboxStore,
  ids: readonly string[],
  onArrive: (id: string) => void,
  delayMs = DEMO_ARRIVAL_MS,
): () => void {
  if (ids.length === 0) return () => {};
  const timer = setTimeout(() => {
    const id = arrivalTarget(store.get(), ids);
    if (id && store.claimDemoArrival() && store.arrive(id)) onArrive(id);
  }, delayMs);
  return () => clearTimeout(timer);
}
