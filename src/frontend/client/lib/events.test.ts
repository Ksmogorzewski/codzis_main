import { describe, expect, it } from "vitest";
import {
  areaLabel,
  chosenDayLabel,
  countLabel,
  eventCountLabel,
  dateBounds,
  dateTitle,
  dayLine,
  mapsUrl,
  outboundLink,
  priceLabel,
  readAtLabel,
  safeUrl,
  scheduleLabels,
  slotLabel,
  sourceLabel,
} from "./events";
import type { Recommendation } from "./schemas";

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

  it("inny dzień: zakres wyboru (od dziś do 60 dni) i etykieta", () => {
    expect(dateBounds(NOW)).toEqual({ min: "2026-10-17", max: "2026-12-16" });
    expect(chosenDayLabel("2026-10-30", NOW)).toBe("Pt 30.10");
    expect(chosenDayLabel("2026-10-18", NOW)).toBe("Jutro");
    expect(dateTitle("2026-10-30", NOW)).toBe("Co robimy w pt 30.10?");
    expect(dateTitle("2026-10-17", NOW)).toBe("Co robimy dziś?");
    expect(dateTitle("2026-10-18", NOW)).toBe("Co robimy jutro?");
  });

  it("opis obszaru i liczba propozycji", () => {
    expect(areaLabel({ area: "nearby", district: "Wola" })).toBe("w dzielnicy Wola i okolicy");
    expect(areaLabel({ area: "city", district: "Wola" })).toBe("w całej Warszawie");
    expect([1, 3, 12].map(countLabel)).toEqual(["1 propozycja", "3 propozycje", "12 propozycji"]);
    expect([1, 3, 12, 22].map(eventCountLabel)).toEqual(["1 wydarzenie", "3 wydarzenia", "12 wydarzeń", "22 wydarzenia"]);
  });
});

describe("events: szczegóły", () => {
  it("cena: zakres, stała, darmowe z ceny i brak danych", () => {
    expect(priceLabel(item({ price: { min: 0, max: 0, currency: "PLN" } }))).toEqual({ label: "Darmowe", free: true });
    expect(priceLabel(item({ price: { min: 45, max: 45, currency: "PLN" } }))?.label).toBe("45 zł");
    expect(priceLabel(item({ price: { min: null, max: null, currency: "PLN" } }))).toBeNull();
    expect(priceLabel(item({ tags: { cost: "Płatne" } }))).toEqual({ label: "Płatne", free: false });
  });

  it("plan zajęć cyklicznych po polsku", () => {
    expect(
      scheduleLabels([
        { day: "monday", start: "18:00", end: "19:30" },
        { day: "wednesday", start: "07:00", end: null },
        { day: "sunday", start: null, end: null },
        { day: "funday", start: "10:00", end: null },
      ]),
    ).toEqual(["Pon 18:00–19:30", "Śr 07:00", "Nd"]);
  });

  it("czas odczytu i linia daty po warszawsku", () => {
    expect(readAtLabel("2026-10-17T08:05:00Z")).toBe("17.10, 10:05");
    expect(readAtLabel(null)).toBeNull();
    expect(readAtLabel("nie-data")).toBeNull();
    expect(dayLine(NOW)).toBe("Sobota, 17 października");
  });

  it("źródło: organizator albo opis źródła miasta", () => {
    expect(sourceLabel(item())).toBe("Kalendarz wydarzeń m.st. Warszawy");
    expect(sourceLabel(item({ source: "um_sport" }))).toBe("Zajęcia sportowe m.st. Warszawy");
    expect(sourceLabel(item({ origin: "partner", source: "partner", partnerName: "Klub Joga" }))).toBe("Klub Joga");
    expect(sourceLabel(item({ origin: "partner", source: "partner" }))).toBe("Organizator wydarzenia");
    expect(sourceLabel(item({ source: "inne" }))).toBe("dane.um.warszawa.pl");
  });

  it("link zewnętrzny: bilet ma pierwszeństwo, tylko http(s)", () => {
    expect(outboundLink(item({ ticketUrl: "https://bilety.pl/1", url: "https://um.pl" }))).toEqual({
      kind: "ticket",
      label: "Kup bilet",
      href: "https://bilety.pl/1",
    });
    expect(outboundLink(item({ ticketUrl: "javascript:x", url: "http://um.pl/e" }))).toEqual({
      kind: "page",
      label: "Zobacz szczegóły",
      href: "http://um.pl/e",
    });
    expect(outboundLink(item())).toBeNull();
  });
});
