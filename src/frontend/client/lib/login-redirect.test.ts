import { isRedirect } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";
import { afterLoginTarget, requireSession } from "./login-redirect";

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
