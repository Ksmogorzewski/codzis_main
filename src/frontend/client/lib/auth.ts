// Logowanie przez Cognito bez SDK.
//   - e-mail + hasło: API Cognito wprost z przeglądarki (USER_PASSWORD_AUTH; rejestracja z kodem z e-maila)
//   - Google: Hosted UI Cognito, kod autoryzacyjny + PKCE, powrót na tę samą stronę
// Sesja w localStorage, odświeżanie tokenów przez REFRESH_TOKEN_AUTH.
import { readJson, writeJson } from "../../shared/storage";
import { config } from "./config";
import { decodeJwt, pkceChallenge, randomString } from "./crypto";

const SESSION_KEY = "warsawnow-session";
const PKCE_KEY = "warsawnow-pkce";

type Session = { idToken: string; accessToken: string; refreshToken?: string; expiresAt: number; method: "password" | "google" };
type AuthResult = { IdToken: string; AccessToken: string; RefreshToken?: string; ExpiresIn: number };

export class AuthError extends Error {
  constructor(public code: string, message?: string) {
    super(message || code);
  }
}

const MESSAGES: Record<string, string> = {
  NotAuthorizedException: "Nieprawidłowy e-mail lub hasło.",
  UserNotFoundException: "Nieprawidłowy e-mail lub hasło.",
  UserNotConfirmedException: "Potwierdź adres e-mail kodem, który wysłaliśmy.",
  UsernameExistsException: "Konto z tym adresem e-mail już istnieje – zaloguj się.",
  InvalidPasswordException: "Hasło musi mieć min. 8 znaków, w tym małą literę i cyfrę.",
  InvalidParameterException: "Sprawdź wpisane dane.",
  CodeMismatchException: "Nieprawidłowy kod. Sprawdź e-mail i spróbuj ponownie.",
  ExpiredCodeException: "Kod wygasł – wyślij nowy.",
  LimitExceededException: "Za dużo prób. Spróbuj ponownie za kilka minut.",
  TooManyRequestsException: "Za dużo prób. Spróbuj ponownie za chwilę.",
  TooManyFailedAttemptsException: "Za dużo nieudanych prób. Spróbuj później.",
  CodeDeliveryFailureException: "Nie udało się wysłać e-maila z kodem. Spróbuj później.",
  PasswordResetRequiredException: "Ustaw nowe hasło – użyj „Nie pamiętasz hasła?”.",
};

async function idp<T>(action: string, body: object): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`https://cognito-idp.${config().region}.amazonaws.com/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": `AWSCognitoIdentityProviderService.${action}` },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError("NetworkError", "Brak połączenia. Sprawdź internet i spróbuj ponownie.");
  }
  const data = (await res.json().catch(() => ({}))) as { __type?: string } & T;
  if (!res.ok) {
    const code = String(data.__type || "Error").split("#").pop()!;
    throw new AuthError(code, MESSAGES[code] || "Coś poszło nie tak. Spróbuj ponownie.");
  }
  return data;
}

// --- sesja ---

const loadSession = () => readJson<Session>("local", SESSION_KEY);

function storeSession(tokens: { idToken: string; accessToken: string; refreshToken?: string; expiresIn: number }, method: Session["method"]) {
  const prev = loadSession();
  const session: Session = {
    idToken: tokens.idToken,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken || prev?.refreshToken, // odświeżenie nie zwraca nowego refresh tokenu
    expiresAt: Date.now() + (tokens.expiresIn || 3600) * 1000,
    method,
  };
  writeJson("local", SESSION_KEY, session);
  return session;
}

const fromResult = (r: AuthResult, method: Session["method"]) =>
  storeSession({ idToken: r.IdToken, accessToken: r.AccessToken, refreshToken: r.RefreshToken, expiresIn: r.ExpiresIn }, method);

export type IdClaims = { sub: string; email?: string; name?: string; picture?: string };

export function currentClaims(): IdClaims | null {
  const session = loadSession();
  return session ? decodeJwt<IdClaims>(session.idToken) : null;
}

// Ważny ID token (odświeżany minutę przed wygaśnięciem) albo null, gdy trzeba się zalogować
export async function getIdToken(): Promise<string | null> {
  const session = loadSession();
  if (!session) return null;
  if (Date.now() < session.expiresAt - 60_000) return session.idToken;
  if (!session.refreshToken) {
    writeJson("local", SESSION_KEY, null);
    return null;
  }
  try {
    const r = await idp<{ AuthenticationResult: AuthResult }>("InitiateAuth", {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      ClientId: config().clientId,
      AuthParameters: { REFRESH_TOKEN: session.refreshToken },
    });
    return fromResult(r.AuthenticationResult, session.method).idToken;
  } catch (e) {
    if (e instanceof AuthError && e.code === "NetworkError") throw e;
    writeJson("local", SESSION_KEY, null);
    return null;
  }
}

// --- e-mail + hasło ---

export async function signIn(email: string, password: string) {
  const r = await idp<{ AuthenticationResult?: AuthResult; ChallengeName?: string }>("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: config().clientId,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  if (!r.AuthenticationResult) {
    throw new AuthError(r.ChallengeName || "Challenge", "To konto wymaga dodatkowego kroku logowania, którego jeszcze nie obsługujemy.");
  }
  fromResult(r.AuthenticationResult, "password");
}

export const signUp = (email: string, password: string) =>
  idp<{ CodeDeliveryDetails?: { Destination?: string } }>("SignUp", {
    ClientId: config().clientId,
    Username: email,
    Password: password,
    UserAttributes: [{ Name: "email", Value: email }],
  });
export const confirmSignUp = (email: string, code: string) =>
  idp("ConfirmSignUp", { ClientId: config().clientId, Username: email, ConfirmationCode: code });
export const resendCode = (email: string) => idp("ResendConfirmationCode", { ClientId: config().clientId, Username: email });
export const forgotPassword = (email: string) => idp("ForgotPassword", { ClientId: config().clientId, Username: email });
export const confirmForgotPassword = (email: string, code: string, password: string) =>
  idp("ConfirmForgotPassword", { ClientId: config().clientId, Username: email, ConfirmationCode: code, Password: password });

// --- Google: Hosted UI + PKCE ---

const redirectUri = () => `${window.location.origin}/`;

export async function signInWithGoogle() {
  const verifier = randomString(64);
  const state = randomString(16);
  writeJson("session", PKCE_KEY, { verifier, state });
  const params = new URLSearchParams({
    response_type: "code",
    client_id: config().clientId,
    redirect_uri: redirectUri(),
    scope: "openid email profile",
    state,
    code_challenge: await pkceChallenge(verifier),
    code_challenge_method: "S256",
    identity_provider: "Google", // od razu do Google, bez ekranu Cognito
  });
  window.location.assign(`https://${config().cognitoDomain}/oauth2/authorize?${params}`);
}

// Powrót z Hosted UI (?code=...&state=... albo ?error=...). true = zalogowano
export async function handleRedirect(): Promise<boolean> {
  const q = new URLSearchParams(window.location.search);
  if (!q.has("code") && !q.has("error")) return false;
  history.replaceState(null, "", window.location.pathname + window.location.hash); // kod jest jednorazowy

  if (q.has("error")) throw new AuthError(q.get("error")!, "Logowanie przez Google nie powiodło się. Spróbuj ponownie.");
  const pkce = readJson<{ verifier: string; state: string }>("session", PKCE_KEY);
  writeJson("session", PKCE_KEY, null);
  if (!pkce || pkce.state !== q.get("state")) throw new AuthError("StateMismatch", "Sesja logowania wygasła. Spróbuj ponownie.");

  const res = await fetch(`https://${config().cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config().clientId,
      code: q.get("code")!,
      redirect_uri: redirectUri(),
      code_verifier: pkce.verifier,
    }),
  });
  const t = (await res.json().catch(() => ({}))) as { id_token: string; access_token: string; refresh_token?: string; expires_in: number; error?: string };
  if (!res.ok) throw new AuthError(t.error || "TokenError", "Logowanie przez Google nie powiodło się. Spróbuj ponownie.");
  storeSession({ idToken: t.id_token, accessToken: t.access_token, refreshToken: t.refresh_token, expiresIn: t.expires_in }, "google");
  return true;
}

// Wylogowanie: unieważnienie refresh tokenu; po Google także wylogowanie z Hosted UI (ciasteczko Cognito).
// true = trwa przekierowanie
export async function signOut(): Promise<boolean> {
  const session = loadSession();
  writeJson("local", SESSION_KEY, null);
  if (session?.refreshToken) {
    const revoke = idp("RevokeToken", { ClientId: config().clientId, Token: session.refreshToken }).catch(() => {});
    await Promise.race([revoke, new Promise((resolve) => setTimeout(resolve, 1500))]);
  }
  if (session?.method === "google") {
    const params = new URLSearchParams({ client_id: config().clientId, logout_uri: redirectUri() });
    window.location.assign(`https://${config().cognitoDomain}/logout?${params}`);
    return true;
  }
  return false;
}
