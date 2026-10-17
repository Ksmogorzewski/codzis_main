import { describe, expect, it } from "vitest";
import { base64url, decodeJwt } from "./crypto";

describe("JWT", () => {
  it("base64url bez paddingu i znaków +/", () => {
    expect(base64url(new Uint8Array([251, 255, 254]))).toBe("-__-");
  });

  it("odczytuje payload JWT z polskimi znakami (UTF-8)", () => {
    const payload = base64url(new TextEncoder().encode(JSON.stringify({ sub: "u1", name: "Łucja Żółć" })));
    expect(decodeJwt<{ name: string }>(`x.${payload}.y`)?.name).toBe("Łucja Żółć");
    expect(decodeJwt("niepoprawny")).toBeNull();
  });
});
