// Wywołania API portalu klienta (API Gateway HTTP z JWT authorizerem Cognito).
// Zwracają Result<T, ApiError>; odpowiedzi sprawdza Zod (lib/schemas.ts).
import type { z } from "zod";
import { getIdToken, refreshSession } from "./auth";
import { config } from "./config";
import { err, ok, type Result } from "./result";
import { ApiErrorBodySchema } from "./schemas";

/**
 * Błąd API. status 0 = brak połączenia. code: z odpowiedzi serwera (np. "needs_onboarding")
 * albo nasz: "network", "unauthorized", "bad_response", "http_<status>".
 */
export type ApiError = { status: number; code: string; message: string; fields: string[] };
export type ApiResult<T> = Result<T, ApiError>;

export const NEEDS_ONBOARDING = "needs_onboarding";

const MESSAGES = {
  network: "Brak połączenia z serwerem. Spróbuj ponownie.",
  unauthorized: "Sesja wygasła – zaloguj się ponownie.",
  badResponse: "Serwer zwrócił nieoczekiwaną odpowiedź. Spróbuj ponownie.",
} as const;

/** Treść błędu {error, fields?, code?} -> ApiError. Czysta funkcja (testy). */
export function toApiError(status: number, body: unknown): ApiError {
  if (status === 401) return { status, code: "unauthorized", message: MESSAGES.unauthorized, fields: [] };
  const parsed = ApiErrorBodySchema.safeParse(body);
  if (parsed.success) {
    const { error, fields, code } = parsed.data;
    return { status, code: code ?? (status === 409 ? NEEDS_ONBOARDING : `http_${status}`), message: error, fields };
  }
  return { status, code: `http_${status}`, message: `Błąd serwera (${status}). Spróbuj ponownie.`, fields: [] };
}

export type ApiDeps = {
  fetch: (url: string, init: RequestInit) => Promise<Response>;
  baseUrl: () => string;
  /** Aktualny ID token; null = brak sesji. Błąd = chwilowy brak sieci przy odświeżaniu. */
  getToken: () => Promise<Result<string | null, unknown>>;
  /** Wymuszone odświeżenie po 401. */
  refreshToken: () => Promise<Result<string | null, unknown>>;
};

const networkError = (): ApiError => ({ status: 0, code: "network", message: MESSAGES.network, fields: [] });
const abortedError = (): ApiError => ({ status: 0, code: "aborted", message: "Zapytanie anulowane.", fields: [] });
const unauthorized = (): ApiError => toApiError(401, null);

export function createApi(deps: ApiDeps) {
  async function send(method: string, path: string, body: unknown, token: string, signal?: AbortSignal): Promise<Response | null> {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    try {
      return await deps.fetch(`${deps.baseUrl()}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      });
    } catch {
      return null;
    }
  }

  async function request<T>(
    method: string,
    path: string,
    body: unknown,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
  ): Promise<ApiResult<T>> {
    const token = await deps.getToken();
    if (token.error !== null) return err(networkError());
    if (token.data === null) return err(unauthorized());

    let res = await send(method, path, body, token.data, signal);
    // 401: token mógł wygasnąć po drodze - jedno odświeżenie i jedno ponowienie.
    if (res?.status === 401) {
      const fresh = await deps.refreshToken();
      if (fresh.error !== null) return err(networkError());
      if (fresh.data === null) return err(unauthorized());
      res = await send(method, path, body, fresh.data, signal);
    }
    if (!res) return err(signal?.aborted ? abortedError() : networkError());

    const json: unknown = await res.json().catch(() => null);
    if (!res.ok) return err(toApiError(res.status, json));
    const parsed = schema.safeParse(json);
    if (!parsed.success) return err({ status: res.status, code: "bad_response", message: MESSAGES.badResponse, fields: [] });
    return ok(parsed.data);
  }

  return {
    apiGet: <T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal) => request("GET", path, undefined, schema, signal),
    apiPut: <T>(path: string, body: unknown, schema: z.ZodType<T>) => request("PUT", path, body, schema),
  };
}

export const { apiGet, apiPut } = createApi({
  fetch: (url, init) => fetch(url, init),
  baseUrl: () => config().apiUrl,
  getToken: getIdToken,
  refreshToken: refreshSession,
});

// --- TanStack Query ---

/** Błąd rzucany do TanStack Query (Query potrzebuje wyjątku); zachowuje status, kod i pola. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: string[];
  constructor(e: ApiError) {
    super(e.message);
    this.name = "ApiRequestError";
    this.status = e.status;
    this.code = e.code;
    this.fields = e.fields;
  }
}

/** W queryFn/mutationFn: dane albo wyjątek ApiRequestError. */
export function unwrap<T>(r: ApiResult<T>): T {
  if (r.error !== null) throw new ApiRequestError(r.error);
  return r.data;
}

/** Błąd, który może zniknąć sam: brak sieci (0) albo 5xx. 4xx i złe dane - nigdy. */
export function isTransientError(error: unknown): boolean {
  if (!(error instanceof ApiRequestError)) return false;
  return error.code !== "bad_response" && error.code !== "aborted" && (error.status === 0 || error.status >= 500);
}

/** Predykat `retry` dla QueryClient: najwyżej jedno ponowienie i tylko błędu przejściowego. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  return failureCount < 1 && isTransientError(error);
}

/** Czy błąd oznacza, że trzeba najpierw wypełnić profil (409 / code "needs_onboarding"). */
export function isNeedsOnboarding(error: unknown): boolean {
  return error instanceof ApiRequestError && (error.code === NEEDS_ONBOARDING || error.status === 409);
}

// --- zimny start Lambdy rekomendacji ---

// Zimny start Lambdy z modelem trwa do ~30 s i HTTP API odpowiada wtedy 503. Ponawiamy z przerwą,
// żeby trafić w rozgrzany już kontener, a nie uruchamiać kolejnego.
export const COLD_START_STATUSES: readonly number[] = [0, 502, 503, 504];
export const COLD_START_DELAYS: readonly number[] = [5000, 10000];

type ColdStartOptions = {
  /** Wywoływane przed każdym ponowieniem (np. komunikat „Dobieramy propozycje…”). */
  onRetry?: (attempt: number) => void;
  signal?: AbortSignal;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
  delays?: readonly number[];
};

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });

/** Wywołuje fn i przy 0/502/503/504 ponawia po 5 s i 10 s. Zwraca ostatni wynik. */
export async function withColdStartRetry<T>(fn: () => Promise<ApiResult<T>>, options: ColdStartOptions = {}): Promise<ApiResult<T>> {
  const { onRetry, signal, sleep = wait, delays = COLD_START_DELAYS } = options;
  let result = await fn();
  for (let attempt = 0; attempt < delays.length; attempt++) {
    if (result.error === null || !COLD_START_STATUSES.includes(result.error.status) || signal?.aborted) return result;
    onRetry?.(attempt + 1);
    await sleep(delays[attempt] ?? 0, signal);
    if (signal?.aborted) return result;
    result = await fn();
  }
  return result;
}

/**
 * Uruchamia fn; jeśli trwa dłużej niż ms, wywołuje onSlow (np. komunikat „Dobieramy propozycje…”,
 * gdy API Gateway trzyma pierwsze zapytanie ~30 s). onDone zawsze po zakończeniu, timer czyszczony.
 */
export async function withSlowHint<T>(fn: () => Promise<T>, ms: number, onSlow: () => void, onDone: () => void): Promise<T> {
  const timer = setTimeout(onSlow, ms);
  try {
    return await fn();
  } finally {
    clearTimeout(timer);
    onDone();
  }
}
