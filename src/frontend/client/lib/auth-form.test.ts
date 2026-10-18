import { describe, expect, it } from "vitest";
import { familyNameError, nameError, normalizeCode, normalizeName, validateAuthForm } from "./auth-form";

const values = {
  name: "Anna",
  familyName: "",
  email: "anna@example.pl", password: "haslo1234", code: "123456", newPassword: "nowehaslo1" };

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

  it("nazwisko opcjonalne, ale poprawne (te same reguły co imię)", () => {
    expect(validateAuthForm("register", { ...values, familyName: "Kowalska-Nowak" })).toBeNull();
    expect(validateAuthForm("register", { ...values, familyName: "Kow4lska" })).toBe(
      "Nazwisko może zawierać tylko litery, spacje i myślnik.",
    );
    expect(validateAuthForm("login", { ...values, familyName: "Kow4lska" })).toBeNull();
    for (const ok of ["", "   ", "Kowalska", "Żółć", " de  la Cruz "]) expect(familyNameError(ok)).toBeNull();
    expect(familyNameError("a".repeat(41))).toBe("Nazwisko może mieć najwyżej 40 znaków.");
    for (const bad of ["-Nowak", "Nowak1", "<b>"]) expect(familyNameError(bad)).not.toBeNull();
  });

  it("rejestracja wymaga imienia", () => {
    expect(validateAuthForm("register", { ...values, name: "   " })).toBe("Podaj imię.");
    expect(validateAuthForm("login", { ...values, name: "" })).toBeNull();
  });

  it("imię: litery (także polskie), spacje i myślnik", () => {
    for (const ok of ["Anna", "Łucja", "Żaneta", "Anna Maria", "Anna-Maria", "  Jan  ", "Zoë", "Ś"]) {
      expect(nameError(ok)).toBeNull();
    }
    expect(nameError("")).toBe("Podaj imię.");
    expect(nameError("   ")).toBe("Podaj imię.");
    for (const bad of ["Anna1", "anna@example.pl", "<b>", "-Anna", "Anna-", "Ann_a"]) {
      expect(nameError(bad)).toBe("Imię może zawierać tylko litery, spacje i myślnik.");
    }
    expect(nameError("a".repeat(41))).toBe("Imię może mieć najwyżej 40 znaków.");
    expect(nameError("a".repeat(40))).toBeNull();
    expect(nameError("Z\u0307aneta")).toBeNull();
  });

  it("rejestracja sprawdza imię tak samo", () => {
    expect(validateAuthForm("register", { ...values, name: "Anna2" })).toBe(
      "Imię może zawierać tylko litery, spacje i myślnik.",
    );
  });

  it("normalizuje imię: przycięte, pojedyncze spacje, NFC, maks. 40 znaków", () => {
    expect(normalizeName("  Anna   Maria ")).toBe("Anna Maria");
    expect(normalizeName("a".repeat(60))).toHaveLength(40);
    expect(normalizeName("   ")).toBe("");
    expect(normalizeName("Z\u0307aneta")).toBe("Żaneta"); // litera + znak łączący (np. z klawiatury macOS)
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
