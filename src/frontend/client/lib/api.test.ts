import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import {
  ApiRequestError,
  createApi,
  isNeedsOnboarding,
  isTransientError,
  pollWhilePreparing,
  shouldRetry,
  toApiError,
  unwrap,
  withColdStartRetry,
  withSlowHint,
} from "./api";
import { err, ok } from "./result";

const Schema = z.object({ value: z.number() });
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setup(responses: Response[], tokens = { get: "t1", fresh: "t2" as string | null }) {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => responses.shift() ?? json(500, {}));
  const refreshToken = vi.fn(async () => ok(tokens.fresh));
  const api = createApi({
    fetch,
    baseUrl: () => "https://api.example",
    getToken: async () => ok(tokens.get),
    refreshToken,
  });
  return { api, fetch, refreshToken };
}

describe("apiGet / apiPut", () => {
  it("wysyła Bearer ID token na apiUrl i sprawdza odpowiedź Zodem", async () => {
    const { api, fetch } = setup([json(200, { value: 1 })]);
    const r = await api.apiGet("/api/me", Schema);
    expect(r).toEqual({ data: { value: 1 }, error: null });
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("https://api.example/api/me");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t1");
  });

  it("PUT wysyła JSON", async () => {
    const { api, fetch } = setup([json(200, { value: 2 })]);
    await api.apiPut("/api/profile", { answers: { who: ["solo"] } }, Schema);
    const init = fetch.mock.calls[0]![1];
    expect(init.method).toBe("PUT");
    expect(init.body).toBe('{"answers":{"who":["solo"]}}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("401: jedno odświeżenie tokenu i ponowienie", async () => {
    const { api, fetch, refreshToken } = setup([json(401, { message: "Unauthorized" }), json(200, { value: 3 })]);
    const r = await api.apiGet("/api/me", Schema);
    expect(r.data).toEqual({ value: 3 });
    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect((fetch.mock.calls[1]![1].headers as Record<string, string>).Authorization).toBe("Bearer t2");
  });

  it("401 po odświeżeniu: błąd unauthorized, bez kolejnych prób", async () => {
    const { api, fetch } = setup([json(401, {}), json(401, {})]);
    const r = await api.apiGet("/api/me", Schema);
    expect(r.error).toMatchObject({ status: 401, code: "unauthorized" });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("brak sesji: unauthorized bez zapytania", async () => {
    const { api, fetch } = setup([], { get: null as unknown as string, fresh: null });
    const r = await api.apiGet("/api/me", Schema);
    expect(r.error?.code).toBe("unauthorized");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("komunikat, pola i kod z serwera", async () => {
    const { api } = setup([json(409, { error: "Uzupełnij profil, żeby zobaczyć rekomendacje.", code: "needs_onboarding" })]);
    const r = await api.apiGet("/api/recommendations", Schema);
    expect(r.error).toEqual({
      status: 409,
      code: "needs_onboarding",
      message: "Uzupełnij profil, żeby zobaczyć rekomendacje.",
      fields: [],
    });
  });

  it("zła odpowiedź: bad_response", async () => {
    const { api } = setup([json(200, { value: "x" })]);
    const r = await api.apiGet("/api/me", Schema);
    expect(r.error?.code).toBe("bad_response");
  });

  it("brak sieci: status 0", async () => {
    const api = createApi({
      fetch: async () => {
        throw new TypeError("Failed to fetch");
      },
      baseUrl: () => "",
      getToken: async () => ok("t"),
      refreshToken: async () => ok("t"),
    });
    const r = await api.apiGet("/api/me", Schema);
    expect(r.error).toMatchObject({ status: 0, code: "network" });
  });
});

describe("anulowanie zapytania", () => {
  it("przekazuje signal do fetch", async () => {
    const { api, fetch } = setup([json(200, { value: 1 })]);
    const ctrl = new AbortController();
    await api.apiGet("/api/me", Schema, ctrl.signal);
    expect(fetch.mock.calls[0]![1].signal).toBe(ctrl.signal);
  });

  it("przerwane zapytanie: code aborted, bez ponowienia", async () => {
    const ctrl = new AbortController();
    const fetch = vi.fn(async () => {
      ctrl.abort();
      throw new DOMException("aborted", "AbortError");
    });
    const api = createApi({ fetch, baseUrl: () => "", getToken: async () => ok("t"), refreshToken: async () => ok("t") });
    const r = await api.apiGet("/api/me", Schema, ctrl.signal);
    expect(r.error).toMatchObject({ code: "aborted" });
    expect(isTransientError(new ApiRequestError(r.error!))).toBe(false);
  });
});

describe("withSlowHint", () => {
  it("po czasie wywołuje onSlow, po zakończeniu czyści", async () => {
    vi.useFakeTimers();
    const onSlow = vi.fn();
    const onDone = vi.fn();
    const p = withSlowHint(() => new Promise<string>((res) => setTimeout(() => res("ok"), 10_000)), 6000, onSlow, onDone);
    await vi.advanceTimersByTimeAsync(5999);
    expect(onSlow).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(onSlow).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(4000);
    expect(await p).toBe("ok");
    expect(onDone).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("szybka odpowiedź: onSlow nie wywołane", async () => {
    vi.useFakeTimers();
    const onSlow = vi.fn();
    await withSlowHint(async () => 1, 6000, onSlow, () => {});
    await vi.advanceTimersByTimeAsync(10_000);
    expect(onSlow).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("toApiError", () => {
  it("400 z polami", () => {
    expect(toApiError(400, { error: "Niepoprawne lub brakujące odpowiedzi", fields: ["who"] })).toEqual({
      status: 400,
      code: "http_400",
      message: "Niepoprawne lub brakujące odpowiedzi",
      fields: ["who"],
    });
  });

  it("odpowiedź bez treści", () => {
    expect(toApiError(503, null)).toMatchObject({ status: 503, code: "http_503" });
  });
});

describe("ponawianie w TanStack Query", () => {
  const e = (status: number, code = `http_${status}`) => new ApiRequestError({ status, code, message: "x", fields: [] });

  it("tylko błędy przejściowe i najwyżej raz", () => {
    expect(shouldRetry(0, e(0, "network"))).toBe(true);
    expect(shouldRetry(0, e(503))).toBe(true);
    expect(shouldRetry(1, e(503))).toBe(false);
    expect(shouldRetry(0, e(400))).toBe(false);
    expect(shouldRetry(0, e(401, "unauthorized"))).toBe(false);
    expect(shouldRetry(0, e(409, "needs_onboarding"))).toBe(false);
    expect(shouldRetry(0, e(200, "bad_response"))).toBe(false);
    expect(shouldRetry(0, new Error("render"))).toBe(false);
  });

  it("unwrap rzuca ApiRequestError z kodem", () => {
    expect(() => unwrap(err({ status: 409, code: "needs_onboarding", message: "m", fields: [] }))).toThrow(ApiRequestError);
    expect(isNeedsOnboarding(e(409, "needs_onboarding"))).toBe(true);
    expect(unwrap(ok(5))).toBe(5);
  });
});

describe("zimny start", () => {
  const fail = (status: number) => err({ status, code: `http_${status}`, message: "x", fields: [] });

  it("503, potem sukces: ponawia po 5 s", async () => {
    const results = [fail(503), ok(1)];
    const sleep = vi.fn(async () => {});
    const onRetry = vi.fn();
    const r = await withColdStartRetry(async () => results.shift()!, { sleep, onRetry });
    expect(r.data).toBe(1);
    expect(sleep).toHaveBeenCalledWith(5000, undefined);
    expect(onRetry).toHaveBeenCalledWith(1);
  });

  it("najwyżej dwa ponowienia (5 s i 10 s), potem ostatni błąd", async () => {
    const fn = vi.fn(async () => fail(504));
    const sleep = vi.fn(async () => {});
    const r = await withColdStartRetry(fn, { sleep });
    expect(fn).toHaveBeenCalledTimes(3);
    expect(sleep.mock.calls.map((c) => (c as unknown[])[0])).toEqual([5000, 10000]);
    expect(r.error?.status).toBe(504);
  });

  it("4xx bez ponawiania", async () => {
    const fn = vi.fn(async () => fail(409));
    await withColdStartRetry(fn, { sleep: async () => {} });
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("zestaw w przygotowaniu (202)", () => {
  const preparing = (retryAfter: number) => ok({ status: "preparing" as const, retryAfter });

  it("pyta ponownie po retryAfter, aż przyjdą karty", async () => {
    const results = [preparing(2), preparing(3), ok({ items: [1] })];
    const sleep = vi.fn(async () => {});
    const r = await pollWhilePreparing(async () => results.shift()!, { sleep });
    expect(r.data).toEqual({ items: [1] });
    expect(sleep.mock.calls.map((c) => (c as unknown[])[0])).toEqual([2000, 3000]);
  });

  it("błąd przerywa czekanie", async () => {
    const results = [preparing(2), err({ status: 409, code: "needs_onboarding", message: "m", fields: [] })];
    const r = await pollWhilePreparing(async () => results.shift()!, { sleep: async () => {} });
    expect(r.error?.code).toBe("needs_onboarding");
  });

  it("za długo w przygotowaniu: błąd zamiast czekania bez końca", async () => {
    let clock = 0;
    const fn = vi.fn(async () => preparing(2));
    const r = await pollWhilePreparing(fn, { sleep: async (ms) => void (clock += ms), now: () => clock, limitMs: 6000 });
    expect(fn).toHaveBeenCalledTimes(4);
    expect(r.error?.code).toBe("preparing_timeout");
  });

  it("anulowanie: bez kolejnych zapytań", async () => {
    const controller = new AbortController();
    const fn = vi.fn(async () => preparing(2));
    const r = await pollWhilePreparing(fn, { signal: controller.signal, sleep: async () => controller.abort() });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(r.error?.code).toBe("aborted");
  });
});
