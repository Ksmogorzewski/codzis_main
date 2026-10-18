import { describe, expect, it } from "vitest";
import { parseConfig } from "./config";

const valid = {
  region: "eu-central-1",
  userPoolId: "eu-central-1_abc",
  clientId: "client",
  cognitoDomain: "x.auth.eu-central-1.amazoncognito.com",
  googleEnabled: false,
  apiUrl: "https://api.example/",
  partnerPortal: "https://partner.example",
};

describe("config", () => {
  it("przyjmuje konfigurację z Terraforma i obcina ukośnik z apiUrl", () => {
    expect(parseConfig(valid).data?.apiUrl).toBe("https://api.example");
  });

  it("klucz Google Maps Embed API opcjonalny (bez niego sam link do Map Google)", () => {
    expect(parseConfig(valid).data?.mapsEmbedKey).toBe("");
    expect(parseConfig({ ...valid, mapsEmbedKey: "AIza-test" }).data?.mapsEmbedKey).toBe("AIza-test");
  });

  it("logowanie Google domyślnie wyłączone (config.js bez tych pól)", () => {
    const withoutGoogle: Record<string, unknown> = { ...valid };
    delete withoutGoogle.cognitoDomain;
    delete withoutGoogle.googleEnabled;
    expect(parseConfig(withoutGoogle).data).toMatchObject({ cognitoDomain: "", googleEnabled: false });
    expect(parseConfig({ ...valid, googleEnabled: true }).data?.googleEnabled).toBe(true);
  });

  it("brak config.js albo brak pól: błąd", () => {
    expect(parseConfig(undefined).error).not.toBeNull();
    expect(parseConfig({ ...valid, clientId: "" }).error).not.toBeNull();
  });
});
