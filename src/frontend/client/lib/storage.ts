// localStorage/sessionStorage potrafią rzucić wyjątek (tryb prywatny, zablokowane dane) - strona działa bez nich
type Kind = "local" | "session";
const store = (kind: Kind) => (kind === "local" ? window.localStorage : window.sessionStorage);

export function readJson<T>(kind: Kind, key: string): T | null {
  try {
    const raw = store(kind).getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function writeJson(kind: Kind, key: string, value: unknown) {
  try {
    if (value === null || value === undefined) store(kind).removeItem(key);
    else store(kind).setItem(key, JSON.stringify(value));
  } catch {
    // brak dostępu do storage - trudno, sesja nie przetrwa przeładowania
  }
}
