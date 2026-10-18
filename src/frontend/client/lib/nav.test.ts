import { describe, expect, it } from "vitest";
import { activeTab, NAV_ITEMS } from "./nav";

describe("nawigacja", () => {
  it("pięć miejsc w stałej kolejności („Twoje” między Popularnymi a Profilem)", () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual(["/", "/eksploruj", "/popularne", "/twoje", "/profil"]);
    expect(NAV_ITEMS.map((i) => i.label)).toEqual(["Dla Ciebie", "Eksploruj", "Popularne", "Twoje", "Profil"]);
  });

  it("aktywna zakładka z adresu", () => {
    expect(activeTab("/")).toBe("/");
    expect(activeTab("/eksploruj")).toBe("/eksploruj");
    expect(activeTab("/popularne")).toBe("/popularne");
    expect(activeTab("/twoje")).toBe("/twoje");
    expect(activeTab("/profil")).toBe("/profil");
  });

  it("szczegóły wydarzenia i nieznane adresy: żadna zakładka", () => {
    expect(activeTab("/wydarzenie/kal-1")).toBeNull();
    expect(activeTab("/wydarzenie/kal-1/ekipa")).toBeNull();
    expect(activeTab("/cos")).toBeNull();
  });
});
