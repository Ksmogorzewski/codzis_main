// Zapisy na wydarzenia („Zapisz” / „Zapisano”), lista zapisanych i Popularne: czyste funkcje
// (optymistyczna zmiana licznika, podpisy). Testy w community.test.ts.
import type { Card } from "./schemas";

/** Stan zapisu na karcie; undefined = nie znamy (karta rekomendacji bez statystyk). */
export type SaveState = { saved?: boolean; saves?: number };
export type KnownSaveState = { saved: boolean; saves: number };

/** Optymistyczna zmiana: ten sam stan = bez zmiany (serwer też jest idempotentny), licznik >= 0. */
export function toggleSave(state: SaveState, want: boolean): KnownSaveState {
  const saved = state.saved ?? false;
  const saves = state.saves ?? 0;
  if (saved === want) return { saved, saves };
  return { saved: want, saves: Math.max(0, saves + (want ? 1 : -1)) };
}

/** Lista kart z nowym stanem zapisu jednej z nich (pozostałe obiekty bez zmian). */
export function patchSaveInList<T extends { id: string } & SaveState>(
  items: readonly T[],
  id: string,
  next: (s: SaveState) => KnownSaveState,
): T[] {
  return items.map((item) => (item.id === id ? { ...item, ...next(item) } : item));
}

type Person = { userId?: string | null; name: string | null; isMe: boolean };

/** Klucz osoby na liście zapisanych: userId; mój wpis - „me” (optymistyczny nie ma id); bez id - pozycja. */
export function personKey(p: Person, index: number): string {
  if (p.isMe) return "me";
  return p.userId ? `u:${p.userId}` : `i:${index}`;
}

/** Lista zapisanych po zmianie stanu: zapis dodaje mnie na początek (najnowsi najpierw), wypisanie usuwa. */
export function patchAttendees<T extends KnownSaveState & { people: Person[] }>(
  list: T,
  next: KnownSaveState,
  myName: string | null,
): T {
  const others = list.people.filter((p) => !p.isMe);
  const mine = list.people.find((p) => p.isMe);
  // imię z tokenu ma pierwszeństwo (serwer mógł zapisać wpis bez imienia: „Ktoś”)
  const me = { ...mine, name: myName ?? mine?.name ?? null, isMe: true };
  const people = next.saved ? [me, ...others] : others;
  return { ...list, saves: next.saves, saved: next.saved, people };
}

export type StatsMap = Record<string, KnownSaveState>;

/** Karty rekomendacji + liczniki z GET /api/events/stats (bez statystyk: te same karty). */
export function withStats(cards: Card[], stats: StatsMap | undefined): Card[] {
  if (!stats) return cards;
  return cards.map((c) => {
    const s = stats[c.id];
    return s ? { ...c, saves: s.saves, saved: s.saved } : c;
  });
}

export const savesLabel = (n: number) => `Zapisanych: ${n}`;

/** Potwierdzenie zapisu: pod jakim imieniem zobaczą mnie inni. */
export const savedAsText = (name: string | null) => (name ? `Zapisano jako ${name}` : "Zapisano");

/** Numer na liście Popularnych (od 1). */
export const rankLabel = (index: number) => String(index + 1);

/** Na liście zapisanych tylko imię; bez imienia „Ktoś”, własny wpis z dopiskiem „Ty”. */
export function attendeeLabel(p: { name: string | null; isMe: boolean }): string {
  const name = p.name?.trim() || null;
  if (p.isMe) return name && name !== "Ktoś" ? `${name} (Ty)` : "Ty";
  return name ?? "Ktoś";
}

const dayMonth = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", day: "2-digit", month: "2-digit" });

/** Okno „najbliższy tydzień” z API -> "19.10 – 25.10" (po warszawsku). */
export function weekLabel(window: { from: string; to: string } | null): string | null {
  if (!window) return null;
  const from = new Date(window.from);
  const to = new Date(window.to);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return null;
  return `${dayMonth.format(from)} – ${dayMonth.format(to)}`;
}
