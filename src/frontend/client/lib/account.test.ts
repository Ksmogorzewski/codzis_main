import { describe, expect, it } from "vitest";
import {
  accountInput,
  ageOn,
  avatarInitials,
  birthDateError,
  fitWithin,
  fullName,
  lastNameError,
  photoFileError,
} from "./account";

const TODAY = "2026-10-18";

describe("dane konta", () => {
  it("body PUT /api/me: nazwisko bez nadmiarowych spacji, puste pola = usuń", () => {
    expect(accountInput("  Kowalska   Nowak ", "1990-05-17")).toEqual({ lastName: "Kowalska Nowak", birthDate: "1990-05-17" });
    expect(accountInput("   ", "")).toEqual({ lastName: null, birthDate: null });
  });

  it("nazwisko do 60 znaków (jak na serwerze)", () => {
    expect(lastNameError("Kowalska")).toBeNull();
    expect(lastNameError(`${"x".repeat(60)}   `)).toBeNull();
    expect(lastNameError("x".repeat(61))).toBe("Nazwisko może mieć najwyżej 60 znaków.");
  });

  it("data urodzenia opcjonalna, prawdziwa, z przeszłości i od 1900 r.", () => {
    expect(birthDateError("", TODAY)).toBeNull();
    expect(birthDateError("1990-05-17", TODAY)).toBeNull();
    expect(birthDateError(TODAY, TODAY)).toBeNull();
    expect(birthDateError("1990-02-30", TODAY)).toBe("Podaj poprawną datę urodzenia.");
    expect(birthDateError("17.05.1990", TODAY)).toBe("Podaj poprawną datę urodzenia.");
    expect(birthDateError("2026-10-19", TODAY)).toBe("Data urodzenia musi być między 1900 r. a dziś.");
    expect(birthDateError("1899-12-31", TODAY)).toBe("Data urodzenia musi być między 1900 r. a dziś.");
  });

  it("wiek w pełnych latach (urodziny jeszcze przed nami albo już były)", () => {
    expect(ageOn("1990-10-18", TODAY)).toBe(36);
    expect(ageOn("1990-10-19", TODAY)).toBe(35);
    expect(ageOn("2000-02-29", "2025-02-28")).toBe(24);
  });

  it("imię i nazwisko oraz inicjały w kółku bez zdjęcia", () => {
    expect(fullName("Anna", "Nowak")).toBe("Anna Nowak");
    expect(fullName("Anna", null)).toBe("Anna");
    expect(fullName(null, null)).toBe("");
    expect(avatarInitials("anna", "nowak")).toBe("AN");
    expect(avatarInitials(null, null)).toBe("?");
  });
});

describe("zdjęcie profilowe", () => {
  it("tylko obrazy do 20 MB (przed zmniejszeniem)", () => {
    expect(photoFileError({ type: "image/heic", size: 3_000_000 })).toBeNull();
    expect(photoFileError({ type: "application/pdf", size: 1000 })).toBe("Wybierz plik ze zdjęciem.");
    expect(photoFileError({ type: "image/jpeg", size: 21 * 1024 * 1024 })).toBe("To zdjęcie jest za duże (maks. 20 MB).");
  });

  it("zmniejszanie do dłuższego boku bez powiększania małych zdjęć", () => {
    expect(fitWithin(4000, 3000, 512)).toEqual({ width: 512, height: 384 });
    expect(fitWithin(1080, 1920, 512)).toEqual({ width: 288, height: 512 });
    expect(fitWithin(300, 200, 512)).toEqual({ width: 300, height: 200 });
  });
});
