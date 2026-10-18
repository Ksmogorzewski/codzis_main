import { describe, expect, it } from "vitest";
import { mainTag, tagChips } from "./tags";

describe("mainTag", () => {
  it("zwraca pierwszy temat", () => {
    expect(mainTag({ theme: ["Muzyka", "Święta i festiwale"] })).toBe("Muzyka");
  });

  it("null bez tematu albo z pustą listą", () => {
    expect(mainTag({})).toBeNull();
    expect(mainTag({ theme: [] })).toBeNull();
  });

  it("'Inne' zostaje, 'Nieznane' pomijamy", () => {
    expect(mainTag({ theme: ["Inne"] })).toBe("Inne");
    expect(mainTag({ theme: ["Nieznane"] })).toBeNull();
  });
});

describe("tagChips", () => {
  it("składa wszystkie tagi w stałej kolejności: temat, format, dla kogo, aktywność, wejście", () => {
    expect(
      tagChips({
        theme: ["Muzyka"],
        format: ["Koncert"],
        audience: ["Dorośli (18-64)", "Seniorzy (65+)"],
        activity_level: "Widz / słuchacz",
        registration: "Wstęp wolny",
      }),
    ).toEqual(["Muzyka", "Koncert", "Dorośli (18-64)", "Seniorzy (65+)", "Widz / słuchacz", "Wstęp wolny"]);
  });

  it("pomija wartości bez informacji i brakujące wymiary", () => {
    expect(
      tagChips({
        theme: ["Sport"],
        registration: "Nieznane",
        activity_level: undefined,
      }),
    ).toEqual(["Sport"]);
    expect(tagChips({})).toEqual([]);
    expect(tagChips({ registration: "Nieznane" })).toEqual([]);
  });

  it("nie dubluje tagów", () => {
    expect(tagChips({ theme: ["Sport"], format: ["Sport"] })).toEqual(["Sport"]);
  });
});
