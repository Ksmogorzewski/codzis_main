// Formatowanie kart rekomendacji. Czas zawsze po warszawsku, niezależnie od strefy przeglądarki.
import { plural } from "../../shared/format";
import type { Recommendation, Recommendations, Slot, When } from "./schemas";

const TZ = "Europe/Warsaw";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_SHORT: Record<string, string> = {
  monday: "pon", tuesday: "wt", wednesday: "śr", thursday: "czw", friday: "pt", saturday: "sob", sunday: "nd",
};

export const WHEN_OPTIONS: { id: When; label: string }[] = [
  { id: "today", label: "Dziś" },
  { id: "tomorrow", label: "Jutro" },
  { id: "weekend", label: "Weekend" },
  { id: "week", label: "7 dni" },
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

// "Inny dzień": od dziś do MAX_DAYS_AHEAD dni naprzód (min/max dla <input type="date">)
export function dateBounds(now: Date): { min: string; max: string } {
  const min = warsawDate(now);
  return { min, max: addDays(min, MAX_DAYS_AHEAD) };
}

// "Pt 30.10" / "Jutro" na przycisku wybranego dnia
export const chosenDayLabel = (iso: string, now: Date) => cap(dayLabel(iso, now));

// Nagłówek ekranu dla wybranego dnia: "Co robimy w pt 30.10?" (dziś / jutro jak w filtrach)
export function dateTitle(iso: string, now: Date): string {
  const label = dayLabel(iso, now);
  return label === "dziś" || label === "jutro" ? `Co robimy ${label}?` : `Co robimy w ${label}?`;
}

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

// "19:00" – godzina startu w tle plakatu karty; bez godziny dla całego dnia, wielodniowych i cyklicznych bez planu
export function posterTime(slot: Slot | null): string | null {
  if (!slot) return null;
  if (slot.recurring) return slot.start ?? null;
  if (slot.allDay) return null;
  const start = new Date(slot.start);
  if (slot.end && warsawDate(new Date(slot.end)) !== warsawDate(start)) return null;
  return timeFormat.format(start);
}

// "Co robimy w weekend?" → mała linia "Co robimy w" i wielkie "weekend?" (nagłówek-plakat ekranu głównego)
export function posterTitle(title: string): { lead: string; big: string } {
  const m = /^(Co robimy(?: w)?) (.+)$/.exec(title);
  return m ? { lead: m[1]!, big: m[2]! } : { lead: "", big: title };
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

// Trasa w Mapach Google (na telefonie od miejsca, w którym jest użytkownik), domyślnie komunikacją miejską
export function mapsUrl(item: Recommendation): string | null {
  if (item.location) {
    return `https://www.google.com/maps/dir/?api=1&destination=${item.location.lat},${item.location.lon}&travelmode=transit`;
  }
  const place = placeLabel(item);
  if (!place || item.online) return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${place}, Warszawa`)}&travelmode=transit`;
}

export function areaLabel(r: Pick<Recommendations, "area" | "district">): string {
  if (r.area === "local" && r.district) return `w dzielnicy ${r.district}`;
  if (r.area === "nearby" && r.district) return `w dzielnicy ${r.district} i okolicy`;
  return "w całej Warszawie";
}

export const countLabel = (n: number) => plural(n, "propozycja", "propozycje", "propozycji");

export const eventCountLabel = (n: number) => plural(n, "wydarzenie", "wydarzenia", "wydarzeń");

// --- szczegóły wydarzenia ---

// ["Pon 18:00–19:30", "Śr 07:00"] – plan zajęć cyklicznych (schedule: day monday..sunday, "HH:MM")
export function scheduleLabels(schedule: Recommendation["schedule"]): string[] {
  return schedule
    .filter((s) => DAY_SHORT[s.day])
    .map((s) => {
      const time = s.start ? ` ${s.start}${s.end ? `–${s.end}` : ""}` : "";
      return cap(`${DAY_SHORT[s.day]}${time}`);
    });
}

const readAtFormat = new Intl.DateTimeFormat("pl-PL", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

// Czas odczytu danych (index.builtAt): "17.10, 10:05" po warszawsku
export function readAtLabel(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = readAtFormat.formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("day")}.${get("month")}, ${get("hour")}:${get("minute")}`;
}

const dayLineFormat = new Intl.DateTimeFormat("pl-PL", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });

// "Sobota, 17 października" – linia daty na ekranie głównym
export const dayLine = (now: Date) => cap(dayLineFormat.format(now));

const SOURCE_LABEL: Record<string, string> = {
  um_kalendarz: "Kalendarz wydarzeń m.st. Warszawy",
  um_sport: "Zajęcia sportowe m.st. Warszawy",
  partner: "Organizator wydarzenia",
};

// Skąd jest karta: nazwa organizatora albo opis zbioru danych miasta
export function sourceLabel(item: Recommendation): string {
  if (item.partnerName) return item.partnerName;
  return SOURCE_LABEL[item.source] ?? "dane.um.warszawa.pl";
}

export type OutboundLink = { kind: "ticket" | "page"; label: string; href: string };

// Główny link wychodzący: bilet, a bez niego strona wydarzenia (tylko http(s))
export function outboundLink(item: Recommendation): OutboundLink | null {
  const ticket = safeUrl(item.ticketUrl);
  if (ticket) return { kind: "ticket", label: "Kup bilet", href: ticket };
  const page = safeUrl(item.url);
  if (page) return { kind: "page", label: "Zobacz szczegóły", href: page };
  return null;
}
