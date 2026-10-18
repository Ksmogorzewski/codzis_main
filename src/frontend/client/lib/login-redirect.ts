// Powrót po logowaniu: link otwarty bez sesji (np. QR „dodaj znajomego”) prowadzi przez /login
// i po zalogowaniu wraca na swój ekran. Tylko ścieżki tej aplikacji (bez otwartego przekierowania).
import { redirect } from "@tanstack/react-router";
import { readJson, writeJson } from "./storage";

export type LoginSearch = { redirect?: string };

/** Ścieżka w aplikacji ("/..."), ale nie "//host" ani sam ekran logowania; inaczej null. */
function safePath(raw: unknown): string | null {
  if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//")) return null;
  if (raw === "/login" || raw.startsWith("/login?")) return null;
  return raw;
}

/** Strażnik tras (beforeLoad w _app): bez sesji -> /login z adresem, na który użytkownik chciał wejść. */
export async function requireSession(auth: { hasSession: () => Promise<boolean> }, href: string): Promise<void> {
  if (await auth.hasSession()) return;
  const target = safePath(href);
  throw redirect({ to: "/login", search: target && target !== "/" ? { redirect: target } : {} });
}

/** Dokąd po zalogowaniu: zapamiętany adres albo strona główna. */
export const afterLoginTarget = (search: LoginSearch): string => safePath(search.redirect) ?? "/";

// Nowe konto z linku w QR idzie najpierw do ankiety (/profil); adres zaproszenia czeka w sessionStorage
// i po zapisie ankiety prowadzi z powrotem na ekran zaproszenia (zamiast na stronę główną).
const TARGET_KEY = "warsawnow.after-onboarding";

type TargetStore = { read: () => unknown; write: (value: string | null) => void };

const sessionTarget: TargetStore = {
  read: () => readJson<unknown>("session", TARGET_KEY),
  write: (value) => writeJson("session", TARGET_KEY, value),
};

/** Zapamiętuje adres na po ankiecie (strony głównej nie trzeba; null czyści). */
export function rememberTarget(target: string | null, store: TargetStore = sessionTarget): void {
  const path = safePath(target);
  store.write(path && path !== "/" ? path : null);
}

/** Zapamiętany adres (jednorazowo - od razu czyszczony) albo null. */
export function takeTarget(store: TargetStore = sessionTarget): string | null {
  const path = safePath(store.read());
  store.write(null);
  return path;
}

// Logowanie Google wychodzi ze strony (Hosted UI) i wraca na stronę główną bez ?redirect=…: ekran czeka
// w sessionStorage tej karty, a strażnik tras (_app.tsx) prowadzi tam po powrocie (nowe konto - przez ankietę).
const GOOGLE_TARGET_KEY = "warsawnow.after-google";

const googleTarget: TargetStore = {
  read: () => readJson<unknown>("session", GOOGLE_TARGET_KEY),
  write: (value) => writeJson("session", GOOGLE_TARGET_KEY, value),
};

/** Przed przekierowaniem do Google: zapamiętuje ekran z ?redirect=… (strony głównej nie trzeba). */
export const rememberGoogleTarget = (search: LoginSearch, store: TargetStore = googleTarget): void =>
  rememberTarget(search.redirect ?? null, store);

/** Po powrocie z Google: zapamiętany ekran (jednorazowo) albo null. */
export const takeGoogleTarget = (store: TargetStore = googleTarget): string | null => takeTarget(store);
