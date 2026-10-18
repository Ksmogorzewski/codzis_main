// Logowanie przez Cognito bez SDK:
//   - e-mail + hasło: API Cognito wprost z przeglądarki (USER_PASSWORD_AUTH), rejestracja z kodem z e-maila, reset hasła;
//   - Google: Hosted UI Cognito, kod autoryzacyjny + PKCE (shared/oauth.ts), powrót na stronę główną.
// Tokeny obu rodzajów sesji odświeża REFRESH_TOKEN_AUTH.
// Sesja w localStorage pod tym samym kluczem co w poprzedniej wersji portalu (zalogowani zostają zalogowani).
import { finishSignIn, logoutUrl, type OAuthApp, type SignInFailure, startSignIn } from "../../shared/oauth";
import { familyNameError, nameError, normalizeName } from "./auth-form";
import { config, loadConfig } from "./config";
import { err, ok, type Result } from "./result";
import { readJson, writeJson } from "./storage";

const SESSION_KEY = "warsawnow-session";
// Odświeżamy minutę przed wygaśnięciem, żeby token nie wygasł w drodze do API.
const REFRESH_MARGIN_MS = 60_000;
// Ile czekamy na unieważnienie refresh tokenu przy wylogowaniu (potem i tak czyścimy sesję).
const REVOKE_TIMEOUT_MS = 1500;

/** method "google" = sesja z Hosted UI: wylogowanie czyści też ciasteczko Cognito. */
export type Session = {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
  method: "password" | "google";
};

type Tokens = { idToken: string; accessToken: string; refreshToken?: string; expiresIn: number };
type AuthenticationResult = { IdToken: string; AccessToken: string; RefreshToken?: string; ExpiresIn: number };

/** Błąd logowania: kod Cognito (np. "UserNotConfirmedException") i komunikat dla użytkownika. */
export type AuthFailure = { code: string; message: string };
export type AuthResult<T> = Result<T, AuthFailure>;

export const NETWORK_ERROR = "NetworkError";
const FALLBACK_MESSAGE = "Coś poszło nie tak. Spróbuj ponownie.";

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
  GoogleDenied: "Logowanie przez Google zostało przerwane. Spróbuj ponownie.",
  GoogleExpired: "Logowanie przez Google wygasło. Spróbuj ponownie.",
  GoogleRejected: "Logowanie przez Google nie powiodło się. Spróbuj ponownie.",
  [NETWORK_ERROR]: "Brak połączenia. Sprawdź internet i spróbuj ponownie.",
};

// Nieudany powrót z Google (shared/oauth.ts) -> kod komunikatu
const GOOGLE_FAILURE_CODES: Record<SignInFailure, string> = {
  denied: "GoogleDenied",
  expired: "GoogleExpired",
  network: NETWORK_ERROR,
  rejected: "GoogleRejected",
};

// --- czyste funkcje (testy w auth.test.ts) ---

/** Komunikat po polsku dla kodu błędu Cognito. */
export function authErrorMessage(code: string): string {
  return MESSAGES[code] ?? FALLBACK_MESSAGE;
}

/** "com.amazonaws...#NotAuthorizedException" -> "NotAuthorizedException". */
export function cognitoErrorCode(type: unknown): string {
  if (typeof type !== "string" || type === "") return "Error";
  return type.split("#").pop() || "Error";
}

export const authFailure = (code: string): AuthFailure => ({ code, message: authErrorMessage(code) });

export const googleFailure = (failure: SignInFailure): AuthFailure => authFailure(GOOGLE_FAILURE_CODES[failure]);

/**
 * Atrybuty przy rejestracji: e-mail, imię (pokazywane innym na listach zapisanych) i - tylko gdy podane -
 * nazwisko (`family_name`; innym backend pokazuje sam inicjał: „Ola K.”).
 */
export function signUpAttributes(email: string, name: string, familyName = ""): { Name: string; Value: string }[] {
  const family = normalizeName(familyName);
  return [
    { Name: "email", Value: email },
    { Name: "name", Value: normalizeName(name) },
    ...(family ? [{ Name: "family_name", Value: family }] : []),
  ];
}

/** Body zapytania Cognito SignUp: e-mail jako login, imię (`name`) i nazwisko (`family_name`) trafiają do ID tokenu. */
export function signUpRequest(clientId: string, email: string, password: string, name: string, familyName = "") {
  return {
    ClientId: clientId,
    Username: email,
    Password: password,
    UserAttributes: signUpAttributes(email, name, familyName),
  };
}

/** Claimy ID tokenu (bez weryfikacji podpisu - to robi API Gateway); zepsuty token - pusty obiekt. */
function tokenClaims(token: string | null): Record<string, unknown> {
  const payload = token?.split(".")[1];
  if (!payload) return {};
  try {
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const claims: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return typeof claims === "object" && claims !== null ? (claims as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

const textClaim = (value: unknown): string | null => {
  const text = typeof value === "string" ? value.split(/\s+/).filter(Boolean).join(" ") : "";
  return text || null;
};

/** Claim "name" z ID tokenu; null = brak imienia. */
export const idTokenName = (token: string | null): string | null => textClaim(tokenClaims(token).name);

/**
 * Imię widoczne dla innych - ta sama reguła co `display_name` w client-api: imię + inicjał nazwiska
 * („Ola K.”); bez nazwiska (albo same spacje) samo imię; bez imienia null.
 */
export function displayName(name: string | null, familyName: string | null): string | null {
  const first = textClaim(name);
  if (!first) return null;
  const initial = [...(textClaim(familyName) ?? "")].find((c) => /\p{L}/u.test(c));
  return initial ? `${first} ${initial.toLocaleUpperCase("pl")}.` : first;
}

/** Imię widoczne dla innych z ID tokenu (claimy `name` i `family_name`). */
export function idTokenDisplayName(token: string | null): string | null {
  const claims = tokenClaims(token);
  return displayName(textClaim(claims.name), textClaim(claims.family_name));
}

/** Co zrobić z zapisaną sesją: użyć tokenu, odświeżyć go albo uznać, że trzeba się zalogować. */
export function tokenStatus(session: Session | null, now: number): "valid" | "refresh" | "signed_out" {
  if (!session) return "signed_out";
  if (now < session.expiresAt - REFRESH_MARGIN_MS) return "valid";
  return session.refreshToken ? "refresh" : "signed_out";
}

/** Nowa sesja z tokenów; odświeżenie nie zwraca nowego refresh tokenu, więc zostawiamy poprzedni. */
export function nextSession(tokens: Tokens, prev: Session | null, now: number, method: Session["method"]): Session {
  return {
    idToken: tokens.idToken,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken || prev?.refreshToken,
    expiresAt: now + (tokens.expiresIn || 3600) * 1000,
    method,
  };
}

// --- Cognito ---

async function idp<T>(action: string, body: object): Promise<AuthResult<T>> {
  let res: Response;
  try {
    res = await fetch(`https://cognito-idp.${config().region}.amazonaws.com/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    return err(authFailure(NETWORK_ERROR));
  }
  const data = (await res.json().catch(() => ({}))) as { __type?: unknown } & T;
  if (!res.ok) return err(authFailure(cognitoErrorCode(data.__type)));
  return ok(data);
}

// --- sesja ---

const loadSession = () => readJson<Session>("local", SESSION_KEY);
const clearSession = () => writeJson("local", SESSION_KEY, null);

function saveSession(tokens: Tokens, method: Session["method"]): Session {
  const session = nextSession(tokens, loadSession(), Date.now(), method);
  writeJson("local", SESSION_KEY, session);
  return session;
}

const storeTokens = (r: AuthenticationResult, method: Session["method"]) =>
  saveSession({ idToken: r.IdToken, accessToken: r.AccessToken, refreshToken: r.RefreshToken, expiresIn: r.ExpiresIn }, method);

let refreshing: Promise<AuthResult<string | null>> | null = null;

/**
 * Odświeża tokeny refresh tokenem. data = nowy ID token albo null (trzeba się zalogować).
 * Błąd NetworkError = chwilowy brak sieci: sesji nie usuwamy. Równoległe wywołania dzielą jedno zapytanie.
 */
export function refreshSession(): Promise<AuthResult<string | null>> {
  if (!refreshing) refreshing = doRefresh().finally(() => (refreshing = null));
  return refreshing;
}

async function doRefresh(): Promise<AuthResult<string | null>> {
  const session = loadSession();
  if (!session?.refreshToken) {
    clearSession();
    return ok(null);
  }
  const r = await idp<{ AuthenticationResult: AuthenticationResult }>("InitiateAuth", {
    AuthFlow: "REFRESH_TOKEN_AUTH",
    ClientId: config().clientId,
    AuthParameters: { REFRESH_TOKEN: session.refreshToken },
  });
  if (r.error !== null) {
    if (r.error.code === NETWORK_ERROR) return r;
    clearSession(); // refresh token odrzucony: sesja skończona
    return ok(null);
  }
  return ok(storeTokens(r.data.AuthenticationResult, session.method).idToken);
}

/** Ważny ID token (odświeżany przed wygaśnięciem) albo null, gdy trzeba się zalogować. */
export async function getIdToken(): Promise<AuthResult<string | null>> {
  const session = loadSession();
  switch (tokenStatus(session, Date.now())) {
    case "valid":
      return ok(session?.idToken ?? null);
    case "refresh":
      return refreshSession();
    case "signed_out":
      clearSession();
      return ok(null);
  }
}

/**
 * Dla strażnika tras: czy użytkownik ma sesję. Przy braku sieci zostawiamy go w aplikacji
 * (zapisana sesja istnieje) - ekran pokaże błąd połączenia zamiast wylogowania.
 */
export async function hasSession(): Promise<boolean> {
  await googleSignInResult(); // powrót z Google zapisuje sesję, zanim ją sprawdzimy
  const r = await getIdToken();
  if (r.error !== null) return loadSession() !== null;
  return r.data !== null;
}

// --- e-mail + hasło ---

export async function signIn(email: string, password: string): Promise<AuthResult<void>> {
  const r = await idp<{ AuthenticationResult?: AuthenticationResult; ChallengeName?: string }>("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: config().clientId,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  if (r.error !== null) return r;
  if (!r.data.AuthenticationResult) {
    return err({
      code: r.data.ChallengeName || "Challenge",
      message: "To konto wymaga dodatkowego kroku logowania, którego jeszcze nie obsługujemy.",
    });
  }
  storeTokens(r.data.AuthenticationResult, "password");
  return ok(undefined);
}

/** Rejestracja; data = adres, na który poszedł kod (zamaskowany przez Cognito, np. a***@e***). */
export async function signUp(
  email: string,
  password: string,
  name: string,
  familyName = "",
): Promise<AuthResult<string>> {
  const badName = nameError(name) ?? familyNameError(familyName);
  if (badName) return err({ code: "InvalidParameterException", message: badName });
  const r = await idp<{ CodeDeliveryDetails?: { Destination?: string } }>(
    "SignUp",
    signUpRequest(config().clientId, email, password, name, familyName),
  );
  if (r.error !== null) return r;
  return ok(r.data.CodeDeliveryDetails?.Destination ?? email);
}

const done = async (r: Promise<AuthResult<unknown>>): Promise<AuthResult<void>> => {
  const result = await r;
  return result.error !== null ? result : ok(undefined);
};

export const confirmSignUp = (email: string, code: string) =>
  done(idp("ConfirmSignUp", { ClientId: config().clientId, Username: email, ConfirmationCode: code }));

export const resendCode = (email: string) =>
  done(idp("ResendConfirmationCode", { ClientId: config().clientId, Username: email }));

export const forgotPassword = (email: string) =>
  done(idp("ForgotPassword", { ClientId: config().clientId, Username: email }));

export const confirmForgotPassword = (email: string, code: string, password: string) =>
  done(
    idp("ConfirmForgotPassword", {
      ClientId: config().clientId,
      Username: email,
      ConfirmationCode: code,
      Password: password,
    }),
  );

// --- Google (Hosted UI + PKCE) ---

/** Przycisk Google tylko, gdy Terraform włączył logowanie Google (google_client_id) i podał domenę Hosted UI. */
export const googleAvailable = () => {
  const r = loadConfig(); // bez config.js po prostu bez Google (błąd konfiguracji pokazuje __root.tsx)
  return r.error === null && r.data.googleEnabled && r.data.cognitoDomain !== "";
};

const googleApp = (): OAuthApp => ({
  domain: config().cognitoDomain,
  clientId: config().clientId,
  // Strona główna: musi być na liście callback_urls i logout_urls (infra/client_auth.tf)
  redirectUri: `${window.location.origin}/`,
  // aws.cognito.signin.user.admin: access token pozwala uzupełnić imię kontu Google bez imienia (setMissingName)
  scope: "openid email profile aws.cognito.signin.user.admin",
});

/** Przekierowanie do Google; powrót na stronę główną z ?code=… (obsługuje googleSignInResult). */
export const signInWithGoogle = () => startSignIn(googleApp());

let googleReturn: Promise<AuthResult<void> | null> | null = null;
let googleError: string | null = null;

/**
 * Powrót z logowania Google (?code=… w adresie): wymiana kodu na sesję, raz na wczytanie strony.
 * null = zwykłe wejście. Czeka na niego strażnik tras (hasSession), zanim sprawdzi sesję.
 */
export function googleSignInResult(): Promise<AuthResult<void> | null> {
  googleReturn ??= completeGoogleSignIn();
  return googleReturn;
}

async function completeGoogleSignIn(): Promise<AuthResult<void> | null> {
  if (!googleAvailable()) return null;
  const r = await finishSignIn(googleApp());
  if (!r) return null;
  if ("failure" in r) {
    googleError = googleFailure(r.failure).message;
    return err(googleFailure(r.failure));
  }
  saveSession(r.tokens, "google");
  return ok(undefined);
}

/** Komunikat nieudanego powrotu z Google dla ekranu logowania - zwracany raz (potem null). */
export async function takeGoogleSignInError(): Promise<string | null> {
  await googleSignInResult();
  const message = googleError;
  googleError = null;
  return message;
}

// --- imię (jednorazowe uzupełnienie dla kont założonych przed polem „Imię”) ---

/** Imię zalogowanego z aktualnego ID tokenu; null = konto bez imienia (albo brak sesji). */
export const currentName = (): string | null => idTokenName(loadSession()?.idToken ?? null);

/** Moje imię tak, jak widzą je inni („Ola K.”) - do podpisów „(Ty)” i „Zapisano jako …”. */
export const currentDisplayName = (): string | null => idTokenDisplayName(loadSession()?.idToken ?? null);

/**
 * Ustawia imię kontu, które go nie ma (UpdateUserAttributes access tokenem), i od razu odświeża
 * tokeny, żeby nowy ID token miał claim "name" (backend kopiuje go do listy zapisanych).
 * Imienia ustawionego raz nie zmieniamy - przy istniejącym nic nie wysyłamy.
 */
export async function setMissingName(raw: string): Promise<AuthResult<void>> {
  const badName = nameError(raw);
  if (badName) return err({ code: "InvalidParameterException", message: badName });
  const name = normalizeName(raw);
  if (currentName()) return ok(undefined);

  const token = await getIdToken(); // odświeża sesję przed wygaśnięciem
  if (token.error !== null) return token;
  const accessToken = loadSession()?.accessToken;
  if (token.data === null || !accessToken) return err(authFailure("NotAuthorizedException"));

  const r = await idp("UpdateUserAttributes", {
    AccessToken: accessToken,
    UserAttributes: [{ Name: "name", Value: name }],
  });
  if (r.error !== null) return r;
  const fresh = await refreshSession();
  if (fresh.error !== null) return fresh;
  return ok(undefined);
}

/**
 * Wylogowanie: czyści sesję i (najwyżej 1,5 s) unieważnia refresh token w Cognito. Po logowaniu Google
 * jeszcze wylogowanie z Hosted UI (przekierowanie i powrót na stronę główną) - inaczej ciasteczko Cognito
 * od razu zalogowałoby tę samą osobę ponownie, bez wyboru konta.
 */
export async function signOut(): Promise<void> {
  const session = loadSession();
  clearSession();
  if (session?.refreshToken) {
    const revoke = idp("RevokeToken", { ClientId: config().clientId, Token: session.refreshToken });
    await Promise.race([revoke, new Promise((resolve) => setTimeout(resolve, REVOKE_TIMEOUT_MS))]);
  }
  if (session?.method === "google" && googleAvailable()) window.location.assign(logoutUrl(googleApp()));
}

/** Uwierzytelnienie w kontekście routera (context.auth). */
export const routerAuth = { hasSession, signOut, takeGoogleSignInError };
export type RouterAuth = typeof routerAuth;
