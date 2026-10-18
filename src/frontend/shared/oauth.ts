// Logowanie przez Google w Cognito Hosted UI, bez SDK: kod autoryzacyjny + PKCE (RFC 7636).
// Wspólne dla portalu klienta i panelu organizatora; tokeny każda aplikacja zapisuje po swojemu.
//   start:  startSignIn() -> /oauth2/authorize?identity_provider=Google (od razu Google, bez ekranu Cognito)
//   powrót: Cognito wraca na redirectUri z ?code=…&state=… -> finishSignIn() wymienia kod na tokeny
//   koniec: logoutUrl() - Cognito czyści swoje ciasteczko sesji i wraca na stronę

export type OAuthApp = {
  domain: string; // domena Hosted UI, np. warsawnow.auth.eu-central-1.amazoncognito.com
  clientId: string;
  redirectUri: string; // dokładnie jak w callback_urls i logout_urls klienta aplikacji (Terraform)
};

export type OAuthTokens = { idToken: string; accessToken: string; refreshToken?: string; expiresIn: number };

/** Dlaczego logowanie się nie udało (komunikat dobiera aplikacja). */
export type SignInFailure = "denied" | "expired" | "network" | "rejected";
export type SignInResult = { tokens: OAuthTokens } | { failure: SignInFailure };

// verifier i state między przekierowaniem do Google a powrotem (ta sama karta)
const PENDING_KEY = "warsawnow-oauth";
type Pending = { verifier: string; state: string };

// --- czyste funkcje (testy w oauth.test.ts) ---

export function base64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export const randomString = (byteLength: number) => base64url(crypto.getRandomValues(new Uint8Array(byteLength)));

/** code_challenge = BASE64URL(SHA-256(verifier)), metoda S256. */
export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

export function authorizeUrl(app: OAuthApp, state: string, challenge: string): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: app.clientId,
    redirect_uri: app.redirectUri,
    scope: "openid email profile",
    identity_provider: "Google",
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return `https://${app.domain}/oauth2/authorize?${params}`;
}

export function logoutUrl(app: OAuthApp): string {
  const params = new URLSearchParams({ client_id: app.clientId, logout_uri: app.redirectUri });
  return `https://${app.domain}/logout?${params}`;
}

/** Parametry powrotu z Hosted UI (location.search); null = zwykłe wejście na stronę. */
export function callbackParams(search: string): { code: string; state: string } | { error: string } | null {
  const q = new URLSearchParams(search);
  const error = q.get("error");
  if (error) return { error };
  const code = q.get("code");
  return code ? { code, state: q.get("state") ?? "" } : null;
}

/** Odpowiedź /oauth2/token -> tokeny; null = błąd albo niepełna odpowiedź. */
export function parseTokens(data: unknown): OAuthTokens | null {
  if (typeof data !== "object" || data === null) return null;
  const t = data as Record<string, unknown>;
  if (typeof t.id_token !== "string" || typeof t.access_token !== "string") return null;
  return {
    idToken: t.id_token,
    accessToken: t.access_token,
    refreshToken: typeof t.refresh_token === "string" ? t.refresh_token : undefined,
    expiresIn: typeof t.expires_in === "number" ? t.expires_in : 3600,
  };
}

// --- przeglądarka ---

function savePending(pending: Pending | null) {
  try {
    if (pending) sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
    else sessionStorage.removeItem(PENDING_KEY);
  } catch {
    // bez sessionStorage powrót z Google skończy się błędem "expired"
  }
}

function loadPending(): Pending | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    return raw ? (JSON.parse(raw) as Pending) : null;
  } catch {
    return null;
  }
}

/** Start logowania: zapamiętuje verifier i state, potem przekierowanie do Google. */
export async function startSignIn(app: OAuthApp): Promise<void> {
  const pending = { verifier: randomString(64), state: randomString(16) };
  savePending(pending);
  window.location.assign(authorizeUrl(app, pending.state, await pkceChallenge(pending.verifier)));
}

/** Powrót z Hosted UI: sprawdza state i wymienia kod na tokeny. null = to nie był powrót z logowania. */
export async function finishSignIn(app: OAuthApp): Promise<SignInResult | null> {
  const callback = callbackParams(window.location.search);
  if (!callback) return null;
  // Kod jest jednorazowy: znika z adresu od razu (odświeżenie nie powtórzy wymiany), #trasa zostaje.
  history.replaceState(null, "", window.location.pathname + window.location.hash);
  const pending = loadPending();
  savePending(null);
  if ("error" in callback) return { failure: "denied" };
  if (!pending || pending.state !== callback.state) return { failure: "expired" };
  return tokenRequest(app, {
    grant_type: "authorization_code",
    code: callback.code,
    redirect_uri: app.redirectUri,
    code_verifier: pending.verifier,
  });
}

/** Nowe ID i access token z refresh tokenu (refresh token się nie zmienia). */
export const refreshTokens = (app: OAuthApp, refreshToken: string) =>
  tokenRequest(app, { grant_type: "refresh_token", refresh_token: refreshToken });

async function tokenRequest(app: OAuthApp, params: Record<string, string>): Promise<SignInResult> {
  let res: Response;
  try {
    res = await fetch(`https://${app.domain}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: app.clientId, ...params }),
    });
  } catch {
    return { failure: "network" };
  }
  const tokens = res.ok ? parseTokens(await res.json().catch(() => null)) : null;
  return tokens ? { tokens } : { failure: "rejected" };
}

/** Unieważnia refresh token; błędy pomijamy (bez sieci token i tak wygaśnie). */
export async function revokeToken(app: OAuthApp, refreshToken: string): Promise<void> {
  try {
    await fetch(`https://${app.domain}/oauth2/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: app.clientId, token: refreshToken }),
    });
  } catch {
    // jw.
  }
}
