// Formatowanie kart rekomendacji. Czas zawsze po warszawsku, niezależnie od strefy przeglądarki.
import { plural } from "../../shared/format";
import type { Recommendation, Recommendations, Slot, When } from "./types";

const TZ = "Europe/Warsaw";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_SHORT: Record<string, string> = {
  monday: "pon", tuesday: "wt", wednesday: "śr", thursday: "czw", friday: "pt", saturday: "sob", sunday: "nd",
};

// Zestawy liczone z góry (w nocy, po zmianie profilu); inny dzień liczy się przy pierwszym wyborze
export const WHEN_OPTIONS: { id: When; label: string }[] = [
  { id: "today", label: "Dziś" },
  { id: "tomorrow", label: "Jutro" },
  { id: "weekend", label: "Weekend" },
];
export const MAX_DAYS_AHEAD = 60; // = MAX_DAYS_AHEAD w src/recommender_api/user_context.py

const dateFormat = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const timeFormat = new Intl.DateTimeFormat("pl-PL", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });

// "2026-10-17" – data w Warszawie
export const warsawDate = (d: Date) => dateFormat.format(d);

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const shortDate = (iso: string) => `${Number(iso.slice(8, 10))}.${iso.slice(5, 7)}`;

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// "dziś" / "jutro" / "sob 24.10"
export function dayLabel(iso: string, now: Date): string {
  const today = warsawDate(now);
  if (iso === today) return "dziś";
  if (iso === addDays(today, 1)) return "jutro";
  const weekday = DAYS[(new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7]!;
  return `${DAY_SHORT[weekday]} ${shortDate(iso)}`;
}

// Zakres dla wyboru "Inny dzień": od dziś do MAX_DAYS_AHEAD dni naprzód
export function dateBounds(now: Date): { min: string; max: string } {
  const min = warsawDate(now);
  return { min, max: addDays(min, MAX_DAYS_AHEAD) };
}

// "Sob 24.10" na przycisku wybranego dnia
export const chosenDayLabel = (iso: string, now: Date) => cap(dayLabel(iso, now));

// "Przygotowane dziś o 05:02"
export const preparedLabel = (generatedAt: string, now: Date) =>
  `Przygotowane ${dayLabel(warsawDate(new Date(generatedAt)), now)} o ${timeFormat.format(new Date(generatedAt))}`;

// "Dziś, 18:00–19:30" / "Trwa do 30.10" / "Pon 19.10, 16:00 · co tydzień"
export function slotLabel(slot: Slot | null, now: Date): string | null {
  if (!slot) return null;
  if (slot.recurring) {
    if (!slot.date) return "Zajęcia cykliczne";
    const time = slot.start ? `, ${slot.start}${slot.end ? `–${slot.end}` : ""}` : "";
    return cap(`${dayLabel(slot.date, now)}${time} · co tydzień`);
  }
  const start = new Date(slot.start);
  const end = slot.end ? new Date(slot.end) : null;
  const startDay = warsawDate(start);
  const endDay = end ? warsawDate(end) : startDay;
  if (endDay !== startDay) {
    return startDay <= warsawDate(now) ? `Trwa do ${shortDate(endDay)}` : cap(`${dayLabel(startDay, now)} – ${shortDate(endDay)}`);
  }
  if (slot.allDay) return cap(`${dayLabel(startDay, now)}, cały dzień`);
  return cap(`${dayLabel(startDay, now)}, ${timeFormat.format(start)}${end ? `–${timeFormat.format(end)}` : ""}`);
}

const money = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2).replace(".", ","));

// Cena zadeklarowana przez organizatora, a bez niej koszt z tagów
export function priceLabel(item: Recommendation): { label: string; free: boolean } | null {
  const { min, max } = item.price ?? { min: null, max: null };
  if (min != null && max != null && max !== min) return { label: `${money(min)}–${money(max)} zł`, free: false };
  const value = min ?? max;
  if (value != null) {
    if (value === 0) return { label: "Darmowe", free: true };
    return { label: min != null && max == null ? `od ${money(value)} zł` : `${money(value)} zł`, free: false };
  }
  if (item.tags.cost === "Bezpłatne") return { label: "Darmowe", free: true };
  if (item.tags.cost === "Płatne") return { label: "Płatne", free: false };
  return null;
}

export function settingInfo(setting?: string): { icon: string; label: string } | null {
  switch (setting) {
    case "W pomieszczeniu":
      return { icon: "roofing", label: "Pod dachem" };
    case "Na zewnątrz":
      return { icon: "park", label: "Plener" };
    case "W pomieszczeniu i na zewnątrz":
      return { icon: "nature_people", label: "Pod dachem i plener" };
  }
  return null;
}

// Linki z danych (także od organizatorów) – tylko http(s)
export function safeUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
  } catch {
    return null;
  }
}

export const placeLabel = (item: Recommendation) => [item.venue?.name, item.venue?.address].filter(Boolean).join(", ");

export function mapsUrl(item: Recommendation): string | null {
  if (item.location) return `https://www.google.com/maps/dir/?api=1&destination=${item.location.lat},${item.location.lon}`;
  const place = placeLabel(item);
  if (!place || item.online) return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${place}, Warszawa`)}`;
}

export function areaLabel(r: Pick<Recommendations, "area" | "district">): string {
  if (r.area === "local" && r.district) return `w dzielnicy ${r.district}`;
  if (r.area === "nearby" && r.district) return `w dzielnicy ${r.district} i okolicy`;
  return "w całej Warszawie";
}

export const countLabel = (n: number) => plural(n, "propozycja", "propozycje", "propozycji");

// Kolor zastępczej "fotki" (paski jak w makiecie), stały dla danego eventu
export function tint(id: string): string {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  return `oklch(0.8 0.08 ${hash} / 0.55)`;
}
