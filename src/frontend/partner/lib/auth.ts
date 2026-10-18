// Logowanie organizatora przez Google (pula Cognito partnerów: infra/partner_auth.tf), kod + PKCE
// (shared/oauth.ts). Konto organizatora zakłada pierwsze GET /me. Bez Google w config.js panel loguje
// kluczem API (lib/session.ts). Tokeny w sessionStorage - jak wcześniej klucz: do zamknięcia karty.
import {
  finishSignIn,
  logoutUrl,
  type OAuthApp,
  type OAuthTokens,
  refreshTokens,
  revokeToken,
  type SignInFailure,
  startSignIn,
} from "../../shared/oauth";
import { config } from "./config";
import { session as apiKeySession } from "./session";

const KEY = "partnerSession";
// Odświeżamy minutę przed wygaśnięciem, żeby token nie wygasł w drodze do API.
const REFRESH_MARGIN_MS = 60_000;
const REVOKE_TIMEOUT_MS = 1500;

type Session = { idToken: string; refreshToken?: string; expiresAt: number };

const FAILURES: Record<SignInFailure, string> = {
  denied: "Logowanie przez Google zostało przerwane. Spróbuj ponownie.",
  expired: "Logowanie przez Google wygasło. Spróbuj ponownie.",
  network: "Brak połączenia z serwerem. Spróbuj ponownie.",
  rejected: "Logowanie przez Google nie powiodło się. Spróbuj ponownie.",
};

export const googleLogin = () => Boolean(config().cognitoDomain && config().clientId);

const app = (): OAuthApp => ({
  domain: config().cognitoDomain ?? "",
  clientId: config().clientId ?? "",
  // Strona główna panelu: musi być w callback_urls i logout_urls (infra/partner_auth.tf)
  redirectUri: `${window.location.origin}/`,
});

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function save(s: Session | null) {
  try {
    if (s) sessionStorage.setItem(KEY, JSON.stringify(s));
    else sessionStorage.removeItem(KEY);
  } catch {
    // bez storage logowanie nie przetrwa przeładowania strony
  }
}

const fromTokens = (t: OAuthTokens, prev: Session | null): Session => ({
  idToken: t.idToken,
  refreshToken: t.refreshToken || prev?.refreshToken, // odświeżenie nie zwraca nowego refresh tokenu
  expiresAt: Date.now() + (t.expiresIn || 3600) * 1000,
});

/** Czy jest zapisane logowanie (Google albo klucz API - zależnie od config.js). */
export const hasLogin = () => (googleLogin() ? load() !== null : apiKeySession.get() !== null);

/** Przekierowanie do Google; powrót na stronę główną panelu z ?code=… (completeSignIn). */
export const signIn = () => startSignIn(app());

/** Powrót z Google: zapisuje sesję. Zwraca komunikat błędu albo null (też gdy to nie był powrót). */
export async function completeSignIn(): Promise<string | null> {
  const r = await finishSignIn(app());
  if (!r) return null;
  if ("failure" in r) return FAILURES[r.failure];
  save(fromTokens(r.tokens, null));
  return null;
}

let refreshing: Promise<string | null> | null = null;

/** Ważny ID token (odświeżany przed wygaśnięciem) albo null, gdy trzeba się zalogować. Bez sieci rzuca. */
export function idToken(): Promise<string | null> {
  const s = load();
  if (!s) return Promise.resolve(null);
  if (Date.now() < s.expiresAt - REFRESH_MARGIN_MS) return Promise.resolve(s.idToken);
  if (!s.refreshToken) {
    save(null);
    return Promise.resolve(null);
  }
  refreshing ??= refresh(s.refreshToken).finally(() => (refreshing = null));
  return refreshing;
}

async function refresh(refreshToken: string): Promise<string | null> {
  const r = await refreshTokens(app(), refreshToken);
  if ("failure" in r) {
    if (r.failure === "network") throw new Error(FAILURES.network); // sesję zostawiamy
    save(null); // refresh token odrzucony: sesja skończona
    return null;
  }
  const next = fromTokens(r.tokens, load());
  save(next);
  return next.idToken;
}

/** Koniec sesji bez przekierowania (np. wygasła): kolejne „Zaloguj się” wróci przez ciasteczko Cognito. */
export const clearSession = () => save(null);

/** Wylogowanie: unieważnia refresh token i wylogowuje z Hosted UI (wraca na stronę logowania panelu). */
export async function signOut(): Promise<void> {
  const s = load();
  save(null);
  if (s?.refreshToken) {
    await Promise.race([revokeToken(app(), s.refreshToken), new Promise((resolve) => setTimeout(resolve, REVOKE_TIMEOUT_MS))]);
  }
  window.location.assign(logoutUrl(app()));
}
