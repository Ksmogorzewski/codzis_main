import { describe, expect, it } from "vitest";
import {
  authorizeUrl,
  base64url,
  callbackParams,
  logoutUrl,
  type OAuthApp,
  parseTokens,
  pkceChallenge,
  randomString,
} from "./oauth";

const app: OAuthApp = {
  domain: "warsawnow.auth.eu-central-1.amazoncognito.com",
  clientId: "client-123",
  redirectUri: "https://portal.waw-out.pl/",
};

describe("PKCE", () => {
  it("base64url bez paddingu i z alfabetem URL", () => {
    expect(base64url(new Uint8Array([0xfb, 0xff]))).toBe("-_8");
  });

  it("verifier z 64 bajtów: 86 znaków base64url (RFC 7636: 43-128)", () => {
    expect(randomString(64)).toMatch(/^[A-Za-z0-9_-]{86}$/);
    expect(randomString(16)).not.toBe(randomString(16));
  });

  it("code_challenge S256 jak w przykładzie z RFC 7636 (dodatek B)", async () => {
    expect(await pkceChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });
});

describe("adresy Hosted UI", () => {
  it("logowanie od razu przez Google, kod + PKCE, powrót na redirectUri", () => {
    const url = new URL(authorizeUrl(app, "st4te", "ch4llenge"));
    expect(url.origin + url.pathname).toBe("https://warsawnow.auth.eu-central-1.amazoncognito.com/oauth2/authorize");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      response_type: "code",
      client_id: "client-123",
      redirect_uri: "https://portal.waw-out.pl/",
      scope: "openid email profile",
      identity_provider: "Google",
      state: "st4te",
      code_challenge: "ch4llenge",
      code_challenge_method: "S256",
    });
  });

  it("wylogowanie z Hosted UI wraca na redirectUri", () => {
    const url = new URL(logoutUrl(app));
    expect(url.origin + url.pathname).toBe("https://warsawnow.auth.eu-central-1.amazoncognito.com/logout");
    expect(url.searchParams.get("client_id")).toBe("client-123");
    expect(url.searchParams.get("logout_uri")).toBe("https://portal.waw-out.pl/");
  });
});

describe("callbackParams", () => {
  it("zwykłe wejście na stronę: null", () => {
    expect(callbackParams("")).toBeNull();
    expect(callbackParams("?id=pay-1")).toBeNull();
  });

  it("powrót z kodem i state", () => {
    expect(callbackParams("?code=abc&state=xyz")).toEqual({ code: "abc", state: "xyz" });
    expect(callbackParams("?code=abc")).toEqual({ code: "abc", state: "" });
  });

  it("błąd z Hosted UI (np. przerwane logowanie) ma pierwszeństwo przed kodem", () => {
    expect(callbackParams("?error=access_denied&error_description=x")).toEqual({ error: "access_denied" });
    expect(callbackParams("?code=abc&error=invalid_request")).toEqual({ error: "invalid_request" });
  });
});

describe("parseTokens", () => {
  it("odpowiedź na kod: wszystkie tokeny", () => {
    const tokens = parseTokens({ id_token: "id", access_token: "acc", refresh_token: "ref", expires_in: 3600 });
    expect(tokens).toEqual({ idToken: "id", accessToken: "acc", refreshToken: "ref", expiresIn: 3600 });
  });

  it("odświeżenie bez nowego refresh tokenu", () => {
    expect(parseTokens({ id_token: "id", access_token: "acc", expires_in: 60 })?.refreshToken).toBeUndefined();
  });

  it("niepełna albo zła odpowiedź: null", () => {
    expect(parseTokens({ access_token: "acc", expires_in: 60 })).toBeNull();
    expect(parseTokens({ error: "invalid_grant" })).toBeNull();
    expect(parseTokens(null)).toBeNull();
    expect(parseTokens("x")).toBeNull();
  });
});
