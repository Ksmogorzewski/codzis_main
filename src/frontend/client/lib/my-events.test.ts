import { describe, expect, it } from "vitest";
import { toggleSave } from "./community";
import { groupMyEvents, pastSlotLabel, patchMyEvents } from "./my-events";
import { MyEventsSchema } from "./schemas";

const raw = (id: string, past: boolean, start: string) => ({
  id,
  title: `Wydarzenie ${id}`,
  slot: { start, end: null, allDay: false },
  saves: 2,
  saved: true,
  past,
  savedAt: "2026-10-14T09:00:00Z",
});

describe("GET /api/me/events (schemat)", () => {
  it("karta z flagą past i czasem zapisu; zepsute karty pomijane", () => {
    const data = MyEventsSchema.parse({
      items: [raw("a", false, "2026-10-18T19:00:00+02:00"), { id: 1 }, raw("b", true, "2026-10-13T10:00:00+02:00")],
    });
    expect(data.items.map((c) => [c.id, c.past, c.saved, c.savedAt])).toEqual([
      ["a", false, true, "2026-10-14T09:00:00Z"],
      ["b", true, true, "2026-10-14T09:00:00Z"],
    ]);
  });

  it("brak past i savedAt (starszy backend) = nadchodzące, bez daty zapisu", () => {
    const { items } = MyEventsSchema.parse({ items: [{ id: "a", title: "A" }] });
    expect(items[0]).toMatchObject({ past: false, savedAt: null });
    expect(MyEventsSchema.parse({}).items).toEqual([]);
  });
});

describe("groupMyEvents", () => {
  it("dzieli na nadchodzące i minione, zachowując kolejność z API", () => {
    const { items } = MyEventsSchema.parse({
      items: [
        raw("dzis", false, "2026-10-18T19:00:00+02:00"),
        raw("sobota", false, "2026-10-24T10:00:00+02:00"),
        raw("wczoraj", true, "2026-10-17T10:00:00+02:00"),
        raw("tydzien-temu", true, "2026-10-11T10:00:00+02:00"),
      ],
    });
    const groups = groupMyEvents(items);
    expect(groups.upcoming.map((c) => c.id)).toEqual(["dzis", "sobota"]);
    expect(groups.past.map((c) => c.id)).toEqual(["wczoraj", "tydzien-temu"]);
  });

  it("pusto", () => {
    expect(groupMyEvents([])).toEqual({ upcoming: [], past: [] });
  });
});

describe("patchMyEvents (optymistyczny zapis / wypisanie)", () => {
  const list = MyEventsSchema.parse({
    items: [raw("a", false, "2026-10-18T19:00:00+02:00"), raw("b", false, "2026-10-19T19:00:00+02:00")],
  });

  it("wypisanie usuwa wydarzenie z listy", () => {
    const next = patchMyEvents(list, "a", (s) => toggleSave(s, false));
    expect(next.items.map((c) => c.id)).toEqual(["b"]);
  });

  it("zapis zmienia licznik, nie dodaje (nowe wydarzenie dociąga odświeżenie listy)", () => {
    const next = patchMyEvents(list, "b", () => ({ saved: true, saves: 7 }));
    expect(next.items.map((c) => [c.id, c.saves])).toEqual([
      ["a", 2],
      ["b", 7],
    ]);
    expect(patchMyEvents(list, "nowe", () => ({ saved: true, saves: 1 })).items).toHaveLength(2);
  });
});

describe("pastSlotLabel (minione)", () => {
  const now = new Date("2026-10-18T12:00:00+02:00"); // niedziela

  it("dzień zakończenia, bez „Trwa do” i godzin", () => {
    expect(pastSlotLabel({ start: "2026-10-13T10:00:00+02:00", end: "2026-10-13T12:00:00+02:00", allDay: false }, now)).toBe(
      "Zakończone · Wt 13.10",
    );
    expect(pastSlotLabel({ start: "2026-10-01T10:00:00+02:00", end: "2026-10-17T18:00:00+02:00", allDay: false }, now)).toBe(
      "Zakończone · Sob 17.10",
    );
    expect(pastSlotLabel({ start: "2026-10-18T08:00:00+02:00", end: null, allDay: false }, now)).toBe("Zakończone · Dziś");
  });

  it("bez terminu (zajęcia bez harmonogramu): samo „Termin minął”", () => {
    expect(pastSlotLabel(null, now)).toBe("Termin minął");
    expect(pastSlotLabel({ recurring: true, date: null, day: null, start: null, end: null }, now)).toBe("Termin minął");
  });
});
