import { describe, expect, it } from "vitest";
import { areaLabel, countLabel, mapsUrl, priceLabel, safeUrl, slotLabel } from "./events";
import type { Recommendation } from "./types";

// sobota 17.10.2026, 17:40 w Warszawie
const NOW = new Date("2026-10-17T15:40:00Z");

const item = (over: Partial<Recommendation> = {}): Recommendation => ({
  id: "kal-1", title: "Koncert", lead: "", url: null, ticketUrl: null, imageUrl: null, origin: "um_warszawa",
  source: "um_kalendarz", kind: "event", partnerName: null, district: "Wola", venue: null, location: null,
  online: false, slot: null, schedule: [], price: null, tags: {}, reason: "", reasonSource: "rules", score: 0.5,
  ...over,
});

describe("events", () => {
  it("termin w wybranym oknie, po warszawsku", () => {
    expect(slotLabel({ start: "2026-10-17T19:00:00+02:00", end: "2026-10-17T21:00:00+02:00", allDay: false }, NOW)).toBe("Dziś, 19:00–21:00");
    expect(slotLabel({ start: "2026-10-18T10:00:00+02:00", end: null, allDay: false }, NOW)).toBe("Jutro, 10:00");
    expect(slotLabel({ start: "2026-10-24T00:00:00+02:00", end: null, allDay: true }, NOW)).toBe("Sob 24.10, cały dzień");
    expect(slotLabel({ start: "2026-10-01T10:00:00+02:00", end: "2026-11-15T18:00:00+01:00", allDay: false }, NOW)).toBe("Trwa do 15.11");
    expect(slotLabel({ start: "2026-10-23T10:00:00+02:00", end: "2026-10-25T22:00:00+02:00", allDay: false }, NOW)).toBe("Pt 23.10 – 25.10");
    expect(slotLabel({ recurring: true, date: "2026-10-19", day: "monday", start: "16:00", end: null }, NOW)).toBe("Pon 19.10, 16:00 · co tydzień");
    expect(slotLabel({ recurring: true, date: null, day: null, start: null, end: null }, NOW)).toBe("Zajęcia cykliczne");
    expect(slotLabel(null, NOW)).toBeNull();
  });

  it("cena: zadeklarowana, potem koszt z tagów", () => {
    expect(priceLabel(item({ price: { min: 30, max: null, currency: "PLN" } }))?.label).toBe("od 30 zł");
    expect(priceLabel(item({ price: { min: 29.5, max: 50, currency: "PLN" } }))?.label).toBe("29,50–50 zł");
    expect(priceLabel(item({ tags: { cost: "Bezpłatne" } }))).toEqual({ label: "Darmowe", free: true });
    expect(priceLabel(item({ tags: { cost: "Nieznane" } }))).toBeNull();
  });

  it("linki tylko http(s), trasa z koordynatów albo adresu", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("https://um.warszawa.pl/x")).toBe("https://um.warszawa.pl/x");
    expect(mapsUrl(item({ location: { lat: 52.2, lon: 21 } }))).toContain("destination=52.2,21");
    expect(mapsUrl(item({ venue: { name: "Hala Koło", address: "Obozowa 60" } }))).toContain("Obozowa%2060%2C%20Warszawa");
    expect(mapsUrl(item())).toBeNull();
  });

  it("opis obszaru i liczba propozycji", () => {
    expect(areaLabel({ area: "nearby", district: "Wola" })).toBe("w dzielnicy Wola i okolicy");
    expect(areaLabel({ area: "city", district: "Wola" })).toBe("w całej Warszawie");
    expect([1, 3, 12].map(countLabel)).toEqual(["1 propozycja", "3 propozycje", "12 propozycji"]);
  });
});
