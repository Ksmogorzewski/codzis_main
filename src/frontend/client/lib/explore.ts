// Eksploruj: filtry w adresie (#/eksploruj?when=…&cat=…&district=…&free=…&indoor=…&q=…), parametry
// GET /api/events i kolejność kart (najbliższy start albo odległość, liczone w przeglądarce).
// Zły lub brakujący parametr wraca do wartości domyślnej, więc ręcznie zmieniony link nie wywraca ekranu.
import { z } from "zod";
import { CATEGORIES, type Category } from "./categories";
import { dateBounds, warsawDate } from "./events";
import { distanceKm, type Point } from "./geo";
import type { Card } from "./schemas";
import { normalizeQuery } from "./search";

export const EXPLORE_WHEN = ["today", "tomorrow", "weekend", "date"] as const;
export type ExploreWhen = (typeof EXPLORE_WHEN)[number];

const MAX_DISTRICT = 60;

// free=true z TanStack Router to już boolean; ręcznie wpisany adres może dać tekst "true"/"1".
const flag = z
  .preprocess((v) => (v === "true" || v === "1" ? true : v === "false" || v === "0" ? false : v), z.boolean())
  .default(false)
  .catch(false);

export const ExploreSearchSchema = z.object({
  when: z.enum(EXPLORE_WHEN).default("today").catch("today"),
  // Tylko przy when=date ("Inny dzień"); zakres sprawdza eventsParams (dziś..+60 dni)
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional().catch(undefined),
  cat: z.enum(CATEGORIES).default("all").catch("all"),
  district: z
    .string()
    .transform((s) => s.trim().slice(0, MAX_DISTRICT) || undefined)
    .optional()
    .catch(undefined),
  free: flag,
  indoor: flag,
  q: z.string().transform(normalizeQuery).default("").catch(""),
});

export type ExploreSearch = z.output<typeof ExploreSearchSchema>;
export const DEFAULT_EXPLORE: ExploreSearch = { when: "today", cat: "all", free: false, indoor: false, q: "" };

export type EventsParams = {
  when: ExploreWhen;
  date?: string;
  cat: Category;
  district?: string;
  free: boolean;
  indoor: boolean;
  q: string;
};

/** Filtry z adresu -> parametry zapytania. "Inny dzień" bez daty albo poza zakresem = dziś. */
export function eventsParams(s: ExploreSearch, now: Date): EventsParams {
  const { min, max } = dateBounds(now);
  const dateOk = s.when === "date" && s.date !== undefined && s.date >= min && s.date <= max;
  return {
    when: s.when === "date" && !dateOk ? "today" : s.when,
    date: dateOk ? s.date : undefined,
    cat: s.cat,
    district: s.district,
    free: s.free,
    indoor: s.indoor,
    q: s.q,
  };
}

/** "/api/events?when=…" tylko z ustawionymi filtrami (kolejność stała = stabilny adres). */
export function eventsPath(p: EventsParams): string {
  const params = new URLSearchParams({ when: p.when });
  if (p.date) params.set("date", p.date);
  if (p.cat !== "all") params.set("cat", p.cat);
  if (p.district) params.set("district", p.district);
  if (p.free) params.set("free", "true");
  if (p.indoor) params.set("indoor", "true");
  if (p.q) params.set("q", p.q);
  return `/api/events?${params}`;
}

// --- kolejność kart ---

const timeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Warsaw",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Początek po warszawsku jako "RRRR-MM-DD GG:MM" (porównywalny jako tekst); null bez terminu. */
export function startKey(card: Pick<Card, "slot">): string | null {
  const slot = card.slot;
  if (!slot) return null;
  if (slot.recurring) return slot.date ? `${slot.date} ${slot.start ?? "00:00"}` : null;
  const start = new Date(slot.start);
  if (Number.isNaN(start.getTime())) return null;
  return `${warsawDate(start)} ${timeFormat.format(start)}`;
}

/** Wydarzenie wielodniowe, które już trwa (np. wystawa): „start” nic nie mówi, więc idzie na koniec. */
function ongoing(card: Pick<Card, "slot">, now: Date): boolean {
  const slot = card.slot;
  if (!slot || slot.recurring || !slot.end) return false;
  const start = new Date(slot.start);
  return start < now && warsawDate(start) !== warsawDate(new Date(slot.end));
}

// Kolejność „po starcie”: najpierw to, co się zaczyna, potem trwające wielodniowe, na końcu bez terminu.
function byStart(now: Date) {
  const rank = (c: Card) => (startKey(c) === null ? 2 : ongoing(c, now) ? 1 : 0);
  return (a: Card, b: Card) => rank(a) - rank(b) || (startKey(a) ?? "").localeCompare(startKey(b) ?? "");
}

/**
 * Karty po najbliższym starcie, a gdy znamy pozycję - po odległości (bez współrzędnych na końcu,
 * między sobą po starcie). Nie zmienia tablicy wejściowej.
 */
export function sortCards(cards: readonly Card[], position: Point | null, now: Date): Card[] {
  const start = byStart(now);
  if (!position) return [...cards].sort(start);
  const km = (c: Card) => (c.location && !c.online ? distanceKm(position, c.location) : Number.POSITIVE_INFINITY);
  return [...cards].sort((a, b) => {
    const da = km(a);
    const db = km(b);
    if (da === db) return start(a, b);
    return da - db;
  });
}

// --- dzielnice ---

type StepLike = { id: string; fields: { id: string; options: { id: string }[] }[] };

const collator = new Intl.Collator("pl");

/** Dzielnice do filtra: z ankiety (krok "where", pole "district"), a bez niej - z wyników. */
export function districtOptions(steps: readonly StepLike[] | undefined, cards: readonly Pick<Card, "district">[]): string[] {
  const field = steps?.find((s) => s.id === "where")?.fields.find((f) => f.id === "district");
  if (field && field.options.length > 0) return field.options.map((o) => o.id);
  const names = new Set(cards.flatMap((c) => (c.district ? [c.district] : [])));
  return [...names].sort(collator.compare);
}
