// Powrót po logowaniu: link otwarty bez sesji (np. QR „dodaj znajomego”) prowadzi przez /login
// i po zalogowaniu wraca na swój ekran. Tylko ścieżki tej aplikacji (bez otwartego przekierowania).
import { redirect } from "@tanstack/react-router";

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
