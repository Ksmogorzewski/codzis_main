import { describe, expect, it } from "vitest";
import { DEFAULT_SEARCH, HomeSearchSchema, normalizeQuery } from "./search";

describe("search", () => {
  it("brak parametrów -> wartości domyślne", () => {
    expect(HomeSearchSchema.parse({})).toEqual(DEFAULT_SEARCH);
    expect(DEFAULT_SEARCH).toEqual({ when: "today", q: "", cat: "all" });
  });

  it("poprawne parametry przechodzą", () => {
    expect(HomeSearchSchema.parse({ when: "weekend", q: "jazz", cat: "kultura" })).toEqual({
      when: "weekend",
      q: "jazz",
      cat: "kultura",
    });
  });

  it("zły parametr wraca do domyślnego, reszta zostaje", () => {
    expect(HomeSearchSchema.parse({ when: "jutro", q: 5, cat: "kino" })).toEqual(DEFAULT_SEARCH);
    expect(HomeSearchSchema.parse({ when: "week", cat: "?" })).toEqual({ when: "week", q: "", cat: "all" });
  });

  it("zapytanie: przycięte, pojedyncze spacje, maks. 120 znaków", () => {
    expect(normalizeQuery("  joga   dla  seniorów ")).toBe("joga dla seniorów");
    expect(normalizeQuery("a".repeat(200))).toHaveLength(120);
    expect(HomeSearchSchema.parse({ q: "  jazz  " }).q).toBe("jazz");
  });
});
