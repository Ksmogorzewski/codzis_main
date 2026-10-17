import { describe, expect, it } from "vitest";
import { findCard } from "./recommendations-cache";
import type { Card, Recommendations } from "./schemas";

const card = (id: string) => ({ id, title: id }) as Card;
const page = (ids: string[], builtAt: string | null): Recommendations =>
  ({ items: ids.map(card), index: { builtAt, events: null } }) as unknown as Recommendations;

describe("findCard", () => {
  it("znajduje kartę w dowolnej odpowiedzi i zwraca jej czas odczytu", () => {
    const found = findCard([undefined, page(["a", "b"], "2026-10-17T08:00:00Z"), page(["c"], "2026-10-17T09:00:00Z")], "c");
    expect(found?.card.id).toBe("c");
    expect(found?.builtAt).toBe("2026-10-17T09:00:00Z");
  });

  it("pierwsze trafienie wygrywa", () => {
    expect(findCard([page(["a"], "1"), page(["a"], "2")], "a")?.builtAt).toBe("1");
  });

  it("brak karty -> null", () => {
    expect(findCard([], "x")).toBeNull();
    expect(findCard([page(["a"], null), undefined], "x")).toBeNull();
  });
});
