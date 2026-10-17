import { describe, expect, it } from "vitest";
import { authErrorMessage, cognitoErrorCode, nextSession, type Session, tokenStatus } from "./auth";

const NOW = 1_800_000_000_000;
const session = (over: Partial<Session> = {}): Session => ({
  idToken: "id",
  accessToken: "access",
  refreshToken: "refresh",
  expiresAt: NOW + 3_600_000,
  method: "password",
  ...over,
});

describe("komunikaty błędów Cognito", () => {
  it("zamienia znane kody na polskie komunikaty", () => {
    expect(authErrorMessage("NotAuthorizedException")).toBe("Nieprawidłowy e-mail lub hasło.");
    expect(authErrorMessage("UserNotFoundException")).toBe("Nieprawidłowy e-mail lub hasło.");
    expect(authErrorMessage("CodeMismatchException")).toBe("Nieprawidłowy kod. Sprawdź e-mail i spróbuj ponownie.");
    expect(authErrorMessage("ExpiredCodeException")).toBe("Kod wygasł – wyślij nowy.");
    expect(authErrorMessage("NetworkError")).toBe("Brak połączenia. Sprawdź internet i spróbuj ponownie.");
  });

  it("nieznany kod: ogólny komunikat", () => {
    expect(authErrorMessage("SomethingNew")).toBe("Coś poszło nie tak. Spróbuj ponownie.");
  });

  it("wyciąga kod z pola __type", () => {
    expect(cognitoErrorCode("com.amazonaws.cognito#UsernameExistsException")).toBe("UsernameExistsException");
    expect(cognitoErrorCode("LimitExceededException")).toBe("LimitExceededException");
    expect(cognitoErrorCode(undefined)).toBe("Error");
    expect(cognitoErrorCode("")).toBe("Error");
  });
});

describe("ważność tokenu", () => {
  it("bez sesji trzeba się zalogować", () => {
    expect(tokenStatus(null, NOW)).toBe("signed_out");
  });

  it("token ważny dłużej niż minutę: używamy go", () => {
    expect(tokenStatus(session({ expiresAt: NOW + 61_000 }), NOW)).toBe("valid");
  });

  it("minutę przed wygaśnięciem i po nim: odświeżamy", () => {
    expect(tokenStatus(session({ expiresAt: NOW + 60_000 }), NOW)).toBe("refresh");
    expect(tokenStatus(session({ expiresAt: NOW - 1 }), NOW)).toBe("refresh");
  });

  it("wygasły token bez refresh tokenu: trzeba się zalogować", () => {
    expect(tokenStatus(session({ expiresAt: NOW - 1, refreshToken: undefined }), NOW)).toBe("signed_out");
  });
});

describe("nowa sesja", () => {
  it("liczy wygaśnięcie z ExpiresIn", () => {
    const s = nextSession({ idToken: "a", accessToken: "b", refreshToken: "r", expiresIn: 3600 }, null, NOW, "password");
    expect(s).toEqual({ idToken: "a", accessToken: "b", refreshToken: "r", expiresAt: NOW + 3_600_000, method: "password" });
  });

  it("odświeżenie bez nowego refresh tokenu zostawia poprzedni", () => {
    const s = nextSession({ idToken: "a2", accessToken: "b2", expiresIn: 3600 }, session(), NOW, "password");
    expect(s.refreshToken).toBe("refresh");
    expect(s.idToken).toBe("a2");
  });

  it("brak ExpiresIn: godzina", () => {
    const s = nextSession({ idToken: "a", accessToken: "b", expiresIn: 0 }, null, NOW, "password");
    expect(s.expiresAt).toBe(NOW + 3_600_000);
  });
});
