import { describe, expect, it } from "vitest";
import { activeTab, NAV_ITEMS } from "./nav";

describe("nawigacja", () => {
  it("pięć miejsc w stałej kolejności („Znajomi” zamiast Eksploruj)", () => {
    expect(NAV_ITEMS.map((i) => i.to)).toEqual(["/", "/znajomi", "/popularne", "/twoje", "/profil"]);
    expect(NAV_ITEMS.map((i) => i.label)).toEqual(["Dla Ciebie", "Znajomi", "Popularne", "Twoje", "Profil"]);
  });

  it("aktywna zakładka z adresu", () => {
    expect(activeTab("/")).toBe("/");
    expect(activeTab("/znajomi")).toBe("/znajomi");
    expect(activeTab("/popularne")).toBe("/popularne");
    expect(activeTab("/twoje")).toBe("/twoje");
    expect(activeTab("/profil")).toBe("/profil");
  });

  it("ekran zaproszenia należy do zakładki Znajomi", () => {
    expect(activeTab("/znajomi/dodaj/WAW-7K2P9X")).toBe("/znajomi");
  });

  it("Eksploruj, szczegóły wydarzenia i nieznane adresy: żadna zakładka", () => {
    expect(activeTab("/eksploruj")).toBeNull();
    expect(activeTab("/wydarzenie/kal-1")).toBeNull();
    expect(activeTab("/wydarzenie/kal-1/ekipa")).toBeNull();
    expect(activeTab("/cos")).toBeNull();
  });
});
