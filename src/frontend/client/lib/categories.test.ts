import { describe, expect, it } from "vitest";
import { categoryOf, filterByCategory } from "./categories";

const card = (id: string, theme?: string[], format?: string[]) => ({ id, tags: { theme, format } });

describe("categories", () => {
  it("sport z tematu albo formatu, kultura z tematu, reszta to rekreacja", () => {
    expect(categoryOf({ theme: ["Sport"] })).toBe("sport");
    expect(categoryOf({ theme: ["Rekreacja i fitness"] })).toBe("sport");
    expect(categoryOf({ format: ["Trening / zajęcia ruchowe"] })).toBe("sport");
    expect(categoryOf({ theme: ["Muzyka"] })).toBe("kultura");
    expect(categoryOf({ theme: ["Muzyka", "Sport"] })).toBe("sport");
    expect(categoryOf({ theme: ["Przyroda i ekologia"] })).toBe("rekreacja");
    expect(categoryOf({})).toBe("rekreacja");
  });

  it("filtr kategorii, 'all' zwraca wszystko w tej samej kolejności", () => {
    const items = [card("a", ["Muzyka"]), card("b", ["Sport"]), card("c", ["Kulinaria"]), card("d", ["Teatr i performans"])];
    expect(filterByCategory(items, "all").map((i) => i.id)).toEqual(["a", "b", "c", "d"]);
    expect(filterByCategory(items, "kultura").map((i) => i.id)).toEqual(["a", "d"]);
    expect(filterByCategory(items, "sport").map((i) => i.id)).toEqual(["b"]);
    expect(filterByCategory(items, "rekreacja").map((i) => i.id)).toEqual(["c"]);
  });
});
