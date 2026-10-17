import { describe, expect, it } from "vitest";
import { activeTab, NAV_ITEMS } from "./nav";

describe("nawigacja", () => {
  it("cztery miejsca w stałej kolejności", () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual(["/", "/eksploruj", "/popularne", "/profil"]);
  });

  it("aktywna zakładka z adresu", () => {
    expect(activeTab("/")).toBe("/");
    expect(activeTab("/eksploruj")).toBe("/eksploruj");
    expect(activeTab("/popularne")).toBe("/popularne");
    expect(activeTab("/profil")).toBe("/profil");
  });

  it("szczegóły wydarzenia i nieznane adresy: żadna zakładka", () => {
    expect(activeTab("/wydarzenie/kal-1")).toBeNull();
    expect(activeTab("/cos")).toBeNull();
  });
});
