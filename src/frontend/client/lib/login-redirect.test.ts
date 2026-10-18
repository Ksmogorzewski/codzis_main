import { isRedirect } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";
import {
  afterLoginTarget,
  rememberGoogleTarget,
  rememberTarget,
  requireSession,
  takeGoogleTarget,
  takeTarget,
} from "./login-redirect";

const auth = (session: boolean) => ({ hasSession: async () => session });

async function caught(p: Promise<unknown>): Promise<unknown> {
  try {
    await p;
  } catch (e) {
    return e;
  }
  return null;
}

describe("invite route keeps code through login redirect", () => {
  it("bez sesji: /login z adresem zaproszenia w search", async () => {
    const e = await caught(requireSession(auth(false), "/znajomi/dodaj/WAW-7K2P9X"));
    expect(isRedirect(e)).toBe(true);
    if (!isRedirect(e)) return;
    expect(e.options.to).toBe("/login");
    expect(e.options.search).toEqual({ redirect: "/znajomi/dodaj/WAW-7K2P9X" });
  });

  it("po logowaniu powrót na ekran zaproszenia", () => {
    expect(afterLoginTarget({ redirect: "/znajomi/dodaj/WAW-7K2P9X" })).toBe("/znajomi/dodaj/WAW-7K2P9X");
  });

  it("z sesją: bez przekierowania", async () => {
    await expect(requireSession(auth(true), "/znajomi/dodaj/WAW-7K2P9X")).resolves.toBeUndefined();
  });

  it("strona główna bez parametru redirect", async () => {
    const e = await caught(requireSession(auth(false), "/"));
    expect(isRedirect(e) && e.options.search).toEqual({});
  });

  it("tylko ścieżki tej aplikacji (bez otwartego przekierowania)", () => {
    expect(afterLoginTarget({})).toBe("/");
    expect(afterLoginTarget({ redirect: "https://zly.example" })).toBe("/");
    expect(afterLoginTarget({ redirect: "//zly.example" })).toBe("/");
    expect(afterLoginTarget({ redirect: "/login" })).toBe("/");
  });
});

describe("adres z zaproszenia przetrwa ankietę (nowe konto z QR)", () => {
  const memory = () => {
    let value: unknown = null;
    return { read: () => value, write: (v: unknown) => void (value = v) };
  };

  it("zapamiętany przed ankietą, odczytany raz po jej zapisie", () => {
    const store = memory();
    rememberTarget("/znajomi/dodaj/WAW-7K2P9X", store);
    expect(takeTarget(store)).toBe("/znajomi/dodaj/WAW-7K2P9X");
    expect(takeTarget(store)).toBeNull();
  });

  it("strona główna i obce adresy nie są zapamiętywane", () => {
    const store = memory();
    rememberTarget("/", store);
    expect(takeTarget(store)).toBeNull();
    store.write("https://zly.example");
    expect(takeTarget(store)).toBeNull();
  });
});

describe("adres z zaproszenia przetrwa logowanie przez Google (wyjście do Hosted UI i powrót)", () => {
  const memory = () => {
    let value: unknown = null;
    return { read: () => value, write: (v: unknown) => void (value = v) };
  };

  it("ekran z ?redirect=… zapamiętany przed wyjściem, odczytany raz po powrocie", () => {
    const store = memory();
    rememberGoogleTarget({ redirect: "/znajomi/dodaj/WAW-7K2P9X" }, store);
    expect(takeGoogleTarget(store)).toBe("/znajomi/dodaj/WAW-7K2P9X");
    expect(takeGoogleTarget(store)).toBeNull();
  });

  it("bez redirect, ze stroną główną albo obcym adresem: nic do zapamiętania", () => {
    const store = memory();
    rememberGoogleTarget({}, store);
    expect(takeGoogleTarget(store)).toBeNull();
    rememberGoogleTarget({ redirect: "//zly.example/x" }, store);
    expect(takeGoogleTarget(store)).toBeNull();
    rememberGoogleTarget({ redirect: "/" }, store);
    expect(takeGoogleTarget(store)).toBeNull();
  });
});
