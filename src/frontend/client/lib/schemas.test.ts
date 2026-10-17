import { describe, expect, it } from "vitest";
import { RecommendationsResponseSchema, RecommendationsSchema } from "./schemas";

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

describe("RecommendationsResponseSchema", () => {
  it("202: zestaw w przygotowaniu, domyślnie pytamy po 2 s", () => {
    expect(RecommendationsResponseSchema.parse({ status: "preparing", retryAfter: 3 })).toEqual({ status: "preparing", retryAfter: 3 });
    expect(RecommendationsResponseSchema.parse({ status: "preparing" })).toEqual({ status: "preparing", retryAfter: 2 });
  });

  it("zestaw: wybrany dzień, updating i cached domyślnie false", () => {
    const r = RecommendationsResponseSchema.parse({ ...base, when: "date", items: [] });
    expect(r).toMatchObject({ when: "date", updating: false, cached: false });
    expect(RecommendationsSchema.parse({ ...base, items: [], updating: true }).updating).toBe(true);
  });
});
