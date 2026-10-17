import { describe, expect, it } from "vitest";
import {
  attendeeLabel,
  patchAttendees,
  patchSaveInList,
  rankLabel,
  savesLabel,
  toggleSave,
  weekLabel,
  withStats,
} from "./community";
import { CardSchema } from "./schemas";

const card = (id: string, over: Record<string, unknown> = {}) => CardSchema.parse({ id, title: id, ...over });

describe("zapis: optymistyczna zmiana stanu", () => {
  it("zapis zwiększa licznik, wypisanie zmniejsza", () => {
    expect(toggleSave({ saved: false, saves: 3 }, true)).toEqual({ saved: true, saves: 4 });
    expect(toggleSave({ saved: true, saves: 4 }, false)).toEqual({ saved: false, saves: 3 });
  });

  it("ten sam stan = bez zmiany (podwójne kliknięcie, idempotentnie jak na serwerze)", () => {
    expect(toggleSave({ saved: true, saves: 4 }, true)).toEqual({ saved: true, saves: 4 });
    expect(toggleSave({ saved: false, saves: 0 }, false)).toEqual({ saved: false, saves: 0 });
  });

  it("licznik nigdy poniżej zera", () => {
    expect(toggleSave({ saved: true, saves: 0 }, false)).toEqual({ saved: false, saves: 0 });
  });

  it("nieznany licznik (karta rekomendacji bez statystyk) liczymy od zera", () => {
    expect(toggleSave({ saved: undefined, saves: undefined }, true)).toEqual({ saved: true, saves: 1 });
  });

  it("zmienia tylko kartę o danym id, reszta to te same obiekty", () => {
    const a = card("a", { saves: 2, saved: false });
    const b = card("b", { saves: 5, saved: false });
    const next = patchSaveInList([a, b], "a", (s) => toggleSave(s, true));
    expect(next[0]).toMatchObject({ id: "a", saves: 3, saved: true });
    expect(next[1]).toBe(b);
  });
});

describe("liczniki i listy", () => {
  it("Zapisanych: N", () => {
    expect(savesLabel(0)).toBe("Zapisanych: 0");
    expect(savesLabel(12)).toBe("Zapisanych: 12");
  });

  it("pozycja w rankingu", () => {
    expect(rankLabel(0)).toBe("1");
    expect(rankLabel(9)).toBe("10");
  });

  it("osoba na liście: Ty / imię / Ktoś", () => {
    expect(attendeeLabel({ name: "Anna", isMe: false })).toBe("Anna");
    expect(attendeeLabel({ name: "  ", isMe: false })).toBe("Ktoś");
    expect(attendeeLabel({ name: null, isMe: false })).toBe("Ktoś");
    expect(attendeeLabel({ name: "Dawid", isMe: true })).toBe("Dawid (Ty)");
    expect(attendeeLabel({ name: null, isMe: true })).toBe("Ty");
    // serwer sam wpisuje „Ktoś” zamiast pustego imienia
    expect(attendeeLabel({ name: "Ktoś", isMe: true })).toBe("Ty");
  });

  it("tydzień popularnych: pon–nd po warszawsku", () => {
    expect(weekLabel({ from: "2026-10-18T22:00:00Z", to: "2026-10-25T22:59:59Z" })).toBe("19.10 – 25.10");
    expect(weekLabel({ from: "2026-10-12", to: "2026-10-18" })).toBe("12.10 – 18.10"); // daty z API
    expect(weekLabel(null)).toBeNull();
  });
});

describe("statystyki dla kart rekomendacji", () => {
  it("dokleja saves/saved po id; karty bez statystyk zostają bez zmian", () => {
    const cards = [card("a"), card("b")];
    const out = withStats(cards, { a: { saves: 7, saved: true } });
    expect(out[0]).toMatchObject({ saves: 7, saved: true });
    expect(out[1]).toBe(cards[1]);
    expect(withStats(cards, undefined)).toBe(cards);
  });
});

describe("lista zapisanych: optymistycznie", () => {
  const list = { saves: 2, saved: false, people: [{ name: "Ola", isMe: false }, { name: null, isMe: false }] };

  it("zapis dodaje mnie na początek, wypisanie usuwa", () => {
    const added = patchAttendees(list, { saved: true, saves: 3 }, "Dawid");
    expect(added).toEqual({ saves: 3, saved: true, people: [{ name: "Dawid", isMe: true }, ...list.people] });
    expect(patchAttendees(added, { saved: false, saves: 2 }, "Dawid")).toEqual(list);
  });

  it("bez zmiany stanu nie dubluje wpisu", () => {
    const mine = { saves: 1, saved: true, people: [{ name: "Dawid", isMe: true }] };
    expect(patchAttendees(mine, { saved: true, saves: 1 }, "Dawid")).toEqual(mine);
  });
});
