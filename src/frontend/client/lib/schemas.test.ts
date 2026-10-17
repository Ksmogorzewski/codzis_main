import { describe, expect, it } from "vitest";
import { RecommendationsSchema } from "./schemas";

const base = { generatedAt: "2026-10-17T10:00:00Z", when: "week" };

describe("RecommendationsSchema", () => {
  it("jedna zepsuta karta nie wywraca odpowiedzi", () => {
    const r = RecommendationsSchema.safeParse({
      ...base,
      items: [{ id: "a", title: "A" }, { id: 5 }, null, { id: "b", title: "B" }],
    });
    expect(r.success).toBe(true);
    expect(r.data?.items.map((c) => c.id)).toEqual(["a", "b"]);
  });

  it("współrzędne ze stringów zamieniane na liczby", () => {
    const r = RecommendationsSchema.safeParse({
      ...base,
      items: [{ id: "a", title: "A", location: { lat: "52.23", lon: "21.01" } }],
    });
    expect(r.data?.items[0]?.location).toEqual({ lat: 52.23, lon: 21.01 });
  });

  it("zepsute współrzędne: karta odrzucona", () => {
    const r = RecommendationsSchema.safeParse({ ...base, items: [{ id: "a", title: "A", location: { lat: "abc", lon: "1" } }] });
    expect(r.data?.items).toEqual([]);
  });
});
