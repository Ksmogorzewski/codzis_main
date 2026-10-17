import { describe, expect, it } from "vitest";
import { creditsLabel, initials, plural, withTimezone } from "./format";

describe("format", () => {
  it("odmienia liczebniki po polsku", () => {
    expect([1, 2, 4, 5, 12, 13, 22, 25].map(creditsLabel)).toEqual([
      "1 kredyt", "2 kredyty", "4 kredyty", "5 kredytów", "12 kredytów", "13 kredytów", "22 kredyty", "25 kredytów",
    ]);
    expect(plural(0, "ogłoszenie", "ogłoszenia", "ogłoszeń")).toBe("0 ogłoszeń");
  });

  it("dokleja offset strefy do datetime-local", () => {
    expect(withTimezone("2027-01-29T19:00")).toMatch(/^2027-01-29T19:00:00[+-]\d{2}:\d{2}$/);
  });

  it("inicjały partnera", () => {
    expect(initials("Fundacja Praska Kultura")).toBe("FP");
    expect(initials("demo")).toBe("D");
  });
});
