// Znajomi: kod do podyktowania, link w QR, podpisy „Ola idzie”, plakietka zaproszeń. Czyste funkcje (testy w friends.test.ts).
import { plural } from "../../shared/format";
import { type ApiResult, NAME_REQUIRED } from "./api";
import type { FriendsOverview } from "./schemas";

/** Alfabet kodu (jak w backendzie: bez 0/O/1/I, które łatwo pomylić przy dyktowaniu). */
const CODE_ALPHABET = /^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{6}$/;
const PREFIX = "WAW";

/**
 * Kod wpisany „byle jak” -> "WAW-XXXXXX" albo null. Te same reguły co `normalize_code` w client-api:
 * wielkie litery, bez spacji i myślników, prefiks WAW opcjonalny, 6 znaków z alfabetu.
 */
export function normalizeCode(raw: string): string | null {
  let s = raw.toUpperCase().replace(/[\s-]/g, "");
  if (s.startsWith(PREFIX)) s = s.slice(PREFIX.length);
  return CODE_ALPHABET.test(s) ? `${PREFIX}-${s}` : null;
}

/** Link z QR: ten sam portal (adres z window.location), ekran zaproszenia na hashu. */
export function inviteLink(code: string, origin: string, pathname: string): string {
  return `${origin}${pathname}#/znajomi/dodaj/${code}`;
}

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, "pl");

/** „Ola idzie”, „Kuba i Ola idą”, „Ola i 2 innych znajomych idzie” (pierwsze imię alfabetycznie); nikt - null. */
export function friendsLine(friends: readonly { name: string }[]): string | null {
  const sorted = [...friends].sort(byName);
  const [first, second] = sorted;
  if (first === undefined) return null;
  if (second === undefined) return `${first.name} idzie`;
  if (sorted.length === 2) return `${first.name} i ${second.name} idą`;
  return `${first.name} i ${sorted.length - 1} innych znajomych idzie`;
}

/** Najbliższy zapis znajomego: pierwsza karta „Znajomi idą” (posortowane po starcie) z jego userId (nie imieniem). */
export function nearestFor<T extends { friends: readonly { userId: string }[] }>(userId: string, items: readonly T[]): T | null {
  return items.find((c) => c.friends.some((f) => f.userId === userId)) ?? null;
}

/**
 * Plakietka „Znajomi”: liczba zaproszeń do mnie z GET /api/friends. Konto bez imienia (409 name_required) -> 0
 * bez błędu, żeby plakietka w nawigacji nie otwierała prośby o imię (robi to dopiero zakładka Znajomi).
 */
export function pendingInvites(r: ApiResult<FriendsOverview>): ApiResult<number> {
  if (r.error?.code === NAME_REQUIRED) return { data: 0, error: null };
  if (r.error !== null) return r;
  return { data: r.data.incoming.length, error: null };
}

/** Podpis plakietki dla czytnika: „2 nowe zaproszenia” (link brzmi wtedy „Znajomi, 2 nowe zaproszenia”). */
export const invitesLabel = (n: number) => plural(n, "nowe zaproszenie", "nowe zaproszenia", "nowych zaproszeń");

/** Macierz QR (true = ciemny moduł) -> ścieżka SVG z kwadratów 1x1 (viewBox = rozmiar macierzy). */
export function qrPath(modules: readonly (readonly boolean[])[]): string {
  let d = "";
  modules.forEach((row, y) => {
    row.forEach((dark, x) => {
      if (dark) d += `M${x} ${y}h1v1h-1z`;
    });
  });
  return d;
}
