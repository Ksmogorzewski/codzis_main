import { formatMoney } from "../../shared/format";
import type { Submission } from "./types";

export const STATUS: Record<Submission["status"], { label: string; tone: "ok" | "info" }> = {
  published: { label: "Opublikowane", tone: "ok" },
  queued: { label: "W kolejce", tone: "info" },
};

export const PAYMENT_STATUS = {
  pending: { label: "Oczekuje", tone: "info" },
  paid: { label: "Opłacona", tone: "ok" },
  cancelled: { label: "Anulowana", tone: "muted" },
} as const;

export const SETTING_ICONS: Record<string, string> = {
  "W pomieszczeniu": "roofing",
  "Na zewnątrz": "park",
  "W pomieszczeniu i na zewnątrz": "swap_horiz",
};

export function priceLabel(ev: Pick<Submission, "declared" | "attributes">): string {
  if (ev.declared?.cost === "Bezpłatne") return "Bezpłatne";
  const price = ev.attributes?.price;
  if (!price || (price.min == null && price.max == null)) return ev.declared?.cost ?? "—";
  const fmt = (v: number) => formatMoney(v, price.currency);
  if (price.min != null && price.max != null && price.min !== price.max) return `${fmt(price.min)} – ${fmt(price.max)}`;
  return `od ${fmt((price.min ?? price.max)!)}`;
}

// Tagi z taggera AI: {theme: [...], audience: [...], cost: "...", ...} -> płaska lista bez "brak informacji"
const EMPTY_TAGS = new Set(["Nieznane", "Brak informacji"]);
export const tagList = (tags?: Submission["tags"]) =>
  Object.values(tags ?? {})
    .flat()
    .filter((t): t is string => typeof t === "string" && !EMPTY_TAGS.has(t));
