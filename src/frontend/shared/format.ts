// Formatowanie po polsku

// plural(5, "kredyt", "kredyty", "kredytów") -> "5 kredytów"
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (n === 1) return `${n} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

export const creditsLabel = (n: number) => plural(n, "kredyt", "kredyty", "kredytów");

export const formatMoney = (amount: number, currency = "PLN") =>
  new Intl.NumberFormat("pl-PL", { style: "currency", currency, maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount);

export const formatDateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" }) : "—";

export const formatDayLabel = (date = new Date()) => {
  const s = date.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
};

// "2027-01-29T19:00" z <input type="datetime-local"> -> ISO z offsetem strefy przeglądarki
export function withTimezone(local: string): string {
  const offset = -new Date(local).getTimezoneOffset();
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  const seconds = local.length === 16 ? ":00" : "";
  return `${local}${seconds}${offset >= 0 ? "+" : "-"}${pad(offset / 60)}:${pad(offset % 60)}`;
}

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("") || "?";
