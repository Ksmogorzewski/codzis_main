// Znajomi: kod do podyktowania, link w QR, podpisy „Ola idzie”. Czyste funkcje (testy w friends.test.ts).

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

const byName = (a: string, b: string) => a.localeCompare(b, "pl");

/** „Ola idzie”, „Kuba i Ola idą”, „Ola i 2 innych znajomych idzie” (pierwsze imię alfabetycznie); nikt - null. */
export function friendsLine(names: readonly string[]): string | null {
  const sorted = [...names].sort(byName);
  const [first, second] = sorted;
  if (first === undefined) return null;
  if (second === undefined) return `${first} idzie`;
  if (sorted.length === 2) return `${first} i ${second} idą`;
  return `${first} i ${sorted.length - 1} innych znajomych idzie`;
}

/** Najbliższy zapis znajomego: pierwsza karta „Znajomi idą” (posortowane po starcie) z jego imieniem. */
export function nearestFor<T extends { friends: readonly string[] }>(name: string, items: readonly T[]): T | null {
  return items.find((c) => c.friends.includes(name)) ?? null;
}

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
