import { describe, expect, it } from "vitest";
import {
  DEFAULT_EXPLORE,
  districtOptions,
  eventsParams,
  eventsPath,
  ExploreSearchSchema,
  sortCards,
  startKey,
} from "./explore";
import { type Card, CardSchema } from "./schemas";

// 18.10.2026, 12:00 w Warszawie (CEST, UTC+2)
const NOW = new Date("2026-10-18T10:00:00Z");

const card = (over: Record<string, unknown>): Card => CardSchema.parse({ id: "x", title: "X", ...over });

describe("Eksploruj: filtry w adresie", () => {
  it("brak parametrów -> wartości domyślne", () => {
    expect(ExploreSearchSchema.parse({})).toEqual(DEFAULT_EXPLORE);
    expect(DEFAULT_EXPLORE).toEqual({ when: "today", cat: "all", free: false, indoor: false, q: "" });
  });

  it("poprawne parametry przechodzą", () => {
    expect(
      ExploreSearchSchema.parse({
        when: "date",
        date: "2026-10-30",
        cat: "sport",
        district: "Mokotów",
        free: true,
        indoor: true,
        q: "  joga  ",
      }),
    ).toEqual({ when: "date", date: "2026-10-30", cat: "sport", district: "Mokotów", free: true, indoor: true, q: "joga" });
  });

  it("zły parametr wraca do domyślnego, reszta zostaje", () => {
    expect(ExploreSearchSchema.parse({ when: "week", cat: "kino", free: "tak", district: 5 })).toEqual(DEFAULT_EXPLORE);
    expect(ExploreSearchSchema.parse({ when: "weekend", district: "  " })).toEqual({ ...DEFAULT_EXPLORE, when: "weekend" });
  });

  it("free/indoor jako tekst z ręcznie wpisanego adresu", () => {
    expect(ExploreSearchSchema.parse({ free: "true", indoor: "1" })).toMatchObject({ free: true, indoor: true });
    expect(ExploreSearchSchema.parse({ free: "false" })).toMatchObject({ free: false });
  });
});

describe("Eksploruj: parametry zapytania", () => {
  it("inny dzień tylko z datą w zakresie (dziś..+60 dni), inaczej dziś", () => {
    const p = (raw: Record<string, unknown>) => eventsParams(ExploreSearchSchema.parse(raw), NOW);
    expect(p({ when: "date", date: "2026-10-30" })).toMatchObject({ when: "date", date: "2026-10-30" });
    expect(p({ when: "date" })).toMatchObject({ when: "today", date: undefined });
    expect(p({ when: "date", date: "2026-10-17" })).toMatchObject({ when: "today", date: undefined });
    expect(p({ when: "date", date: "2027-01-30" })).toMatchObject({ when: "today", date: undefined });
    expect(p({ when: "weekend", date: "2026-10-30" })).toMatchObject({ when: "weekend", date: undefined });
  });

  it("fraza obcięta do 100 znaków (limit serwera)", () => {
    const p = eventsParams({ ...DEFAULT_EXPLORE, q: "a".repeat(120) }, NOW);
    expect(new URLSearchParams(eventsPath(p).split("?")[1]).get("q")).toHaveLength(100);
  });

  it("ścieżka: tylko ustawione filtry", () => {
    expect(eventsPath(eventsParams(DEFAULT_EXPLORE, NOW))).toBe("/api/events?when=today&limit=200");
    const full = eventsParams(
      { when: "date", date: "2026-10-30", cat: "kultura", district: "Wola", free: true, indoor: true, q: "jazz" },
      NOW,
    );
    expect(eventsPath(full)).toBe(
      "/api/events?when=date&date=2026-10-30&cat=kultura&district=Wola&free=true&indoor=true&q=jazz&limit=200",
    );
  });
});

describe("Eksploruj: sortowanie", () => {
  const dated = (id: string, start: string, end: string | null = null, location: unknown = null) =>
    card({ id, slot: { start, end }, location });

  it("klucz startu po warszawsku: wydarzenie i zajęcia cykliczne", () => {
    expect(startKey(dated("a", "2026-10-18T16:00:00Z"))).toBe("2026-10-18 18:00");
    expect(startKey(card({ slot: { recurring: true, date: "2026-10-19", start: "07:30" } }))).toBe("2026-10-19 07:30");
    expect(startKey(card({ slot: { recurring: true, date: "2026-10-19" } }))).toBe("2026-10-19 00:00");
    expect(startKey(card({}))).toBeNull();
  });

  it("bez pozycji: najbliższy start; trwające wielodniowe i bez terminu na końcu", () => {
    const later = dated("later", "2026-10-18T18:00:00Z");
    const soon = dated("soon", "2026-10-18T14:00:00Z");
    const exhibition = dated("exhibition", "2026-09-01T08:00:00Z", "2026-12-31T16:00:00Z");
    const noSlot = card({ id: "noslot" });
    const ids = sortCards([noSlot, later, exhibition, soon], null, NOW).map((c) => c.id);
    expect(ids).toEqual(["soon", "later", "exhibition", "noslot"]);
  });

  it("z pozycją: najbliżej pierwsze, bez współrzędnych na końcu (wg startu)", () => {
    const here = { lat: 52.2297, lon: 21.0122 };
    const near = dated("near", "2026-10-18T18:00:00Z", null, { lat: 52.23, lon: 21.013 });
    const far = dated("far", "2026-10-18T14:00:00Z", null, { lat: 52.3, lon: 21.1 });
    const unknownLate = dated("unknown-late", "2026-10-18T19:00:00Z");
    const unknownSoon = dated("unknown-soon", "2026-10-18T13:00:00Z");
    const ids = sortCards([unknownLate, far, unknownSoon, near], here, NOW).map((c) => c.id);
    expect(ids).toEqual(["near", "far", "unknown-soon", "unknown-late"]);
  });

  it("nie zmienia tablicy wejściowej", () => {
    const input = [dated("b", "2026-10-18T18:00:00Z"), dated("a", "2026-10-18T14:00:00Z")];
    sortCards(input, null, NOW);
    expect(input.map((c) => c.id)).toEqual(["b", "a"]);
  });
});

describe("Eksploruj: lista dzielnic", () => {
  it("z ankiety (krok where, pole district), w kolejności z API", () => {
    const steps = [
      { id: "who", fields: [{ id: "who", options: [{ id: "solo", label: "Sam" }] }] },
      { id: "where", fields: [{ id: "district", options: [{ id: "Wola", label: "Wola" }, { id: "Bemowo", label: "Bemowo" }] }] },
    ];
    expect(districtOptions(steps, [])).toEqual(["Wola", "Bemowo"]);
  });

  it("bez ankiety: unikalne dzielnice z wyników, alfabetycznie po polsku", () => {
    const cards = [card({ district: "Żoliborz" }), card({ district: "Bemowo" }), card({ district: null }), card({ district: "Bemowo" })];
    expect(districtOptions(undefined, cards)).toEqual(["Bemowo", "Żoliborz"]);
  });
});
