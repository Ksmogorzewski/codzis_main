import { describe, expect, it } from "vitest";
import { normalizeCode, validateAuthForm } from "./auth-form";

const values = { email: "anna@example.pl", password: "haslo1234", code: "123456", newPassword: "nowehaslo1" };

describe("formularz logowania", () => {
  it("poprawne dane w każdym kroku", () => {
    for (const mode of ["login", "register", "confirm", "reset", "resetConfirm"] as const) {
      expect(validateAuthForm(mode, values)).toBeNull();
    }
  });

  it("zły e-mail, puste hasło, krótkie hasło", () => {
    expect(validateAuthForm("login", { ...values, email: "anna" })).toBe("Podaj poprawny adres e-mail.");
    expect(validateAuthForm("login", { ...values, password: "" })).toBe("Podaj hasło.");
    expect(validateAuthForm("register", { ...values, password: "krótkie" })).toMatch(/min\. 8 znaków/);
  });

  it("kod musi mieć 6 cyfr", () => {
    expect(validateAuthForm("confirm", { ...values, code: "123" })).toBe("Wpisz 6-cyfrowy kod z e-maila.");
    expect(validateAuthForm("resetConfirm", { ...values, newPassword: "abc" })).toBe("Nowe hasło musi mieć min. 8 znaków.");
  });

  it("kod: same cyfry, najwyżej 6", () => {
    expect(normalizeCode(" 123 456 7")).toBe("123456");
    expect(normalizeCode("ab12")).toBe("12");
  });
});
