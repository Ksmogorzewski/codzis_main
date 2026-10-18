import { describe, expect, it } from "vitest";
import {
  arrivals,
  authorLabel,
  crewSizeLabel,
  HOST,
  hostCard,
  markCrewRead,
  membersLine,
  mergeCrew,
  messagePreview,
  messageTime,
  noticeText,
  otherNames,
  unreadLabel,
  withMessage,
} from "./crew-chat";
import type { Crew, CrewMessage, MyCrew, MyCrews } from "./schemas";

const msg = (id: string, sentAt: string, over: Partial<CrewMessage> = {}): CrewMessage => ({
  id,
  kind: "user",
  userId: "u-2",
  name: "Bartek Z.",
  text: `tekst ${id}`,
  sentAt,
  isMe: false,
  ...over,
});

const crew = (over: Partial<Crew> = {}): Crew => ({
  crew: "001",
  capacity: 4,
  members: [
    { userId: "u-1", name: "Ala N.", isMe: true },
    { userId: "u-2", name: "Bartek Z.", isMe: false },
  ],
  messageCount: 2,
  icebreaker: "Jaka jest Twoja ulubiona ulica lub budynek w Warszawie?",
  answered: false,
  messages: [],
  cursor: null,
  ...over,
});

const T1 = "2026-10-18T16:00:00.000Z";
const T2 = "2026-10-18T16:00:05.000Z";
const T3 = "2026-10-18T16:00:09.000Z";

describe("mergeCrew: kolejne odpowiedzi odpytywania", () => {
  it("pierwsza odpowiedź: wiadomości od najstarszej", () => {
    const next = crew({ messages: [msg("b", T2), msg("a", T1)], cursor: T2 });
    expect(mergeCrew(undefined, next).messages.map((m) => m.id)).toEqual(["a", "b"]);
  });

  it("zapas 15 s z ?after=: powtórki po id znikają, nowe dochodzą na końcu, cursor idzie naprzód", () => {
    const prev = crew({ messages: [msg("a", T1), msg("b", T2)], cursor: T2 });
    const next = crew({ messages: [msg("b", T2), msg("c", T3)], cursor: T3, messageCount: 3 });
    const merged = mergeCrew(prev, next);
    expect(merged.messages.map((m) => m.id)).toEqual(["a", "b", "c"]);
    expect(merged.cursor).toBe(T3);
    expect(merged.messageCount).toBe(3);
  });

  it("odpowiedź bez nowych wiadomości nie cofa cursora", () => {
    const prev = crew({ messages: [msg("c", T3)], cursor: T3 });
    expect(mergeCrew(prev, crew({ messages: [], cursor: T2 })).cursor).toBe(T3);
  });

  it("ta sama chwila: kolejność po id (stała między odświeżeniami)", () => {
    const next = crew({ messages: [msg("001#x2", T1), msg("001#x1", T1)] });
    expect(mergeCrew(undefined, next).messages.map((m) => m.id)).toEqual(["001#x1", "001#x2"]);
  });

  it("inna ekipa (wyjście i ponowne dołączenie) = nowa rozmowa", () => {
    const prev = crew({ messages: [msg("a", T1)], cursor: T1 });
    const merged = mergeCrew(prev, crew({ crew: "002", messages: [msg("z", T3)], cursor: T3 }));
    expect(merged.messages.map((m) => m.id)).toEqual(["z"]);
  });
});

describe("withMessage: moja wysłana wiadomość", () => {
  it("od razu w czacie, odblokowuje lodołamacz", () => {
    const c = withMessage(crew({ messages: [msg("a", T2)] }), msg("m", T1, { isMe: true, userId: "u-1" }));
    expect(c.messages.map((m) => m.id)).toEqual(["m", "a"]);
    expect(c.answered).toBe(true);
    expect(c.messageCount).toBe(3);
  });

  it("ta sama wiadomość już przyszła z odpytywania - bez duplikatu", () => {
    const mine = msg("m", T1, { isMe: true });
    const c = withMessage(crew({ messages: [mine] }), mine);
    expect(c.messages).toHaveLength(1);
    expect(c.messageCount).toBe(2);
  });
});

describe("komunikaty Wodzireja (z danych wydarzenia, bez AI)", () => {
  const info = { category: "Muzyka", place: "Klub Jazzowy, ul. Mazowiecka 1", when: "Dziś, 19:00" };

  it("dołączenie i wyjście: jedna linia, moje w drugiej osobie", () => {
    expect(noticeText(msg("j", T1, { kind: "joined", text: null }))).toBe("Bartek Z. dołącza do ekipy");
    expect(noticeText(msg("j", T1, { kind: "joined", isMe: true }))).toBe("Dołączasz do ekipy");
    expect(noticeText(msg("l", T1, { kind: "left", name: null }))).toBe("Ktoś wychodzi z ekipy");
    expect(noticeText(msg("l", T1, { kind: "left", isMe: true }))).toBe("Wychodzisz z ekipy");
    expect(noticeText(msg("u", T1))).toBeNull();
  });

  it("nowa ekipa: kto zaczął, wielkość ekipy i lodołamacz; punkt i czas zbiórki z wydarzenia", () => {
    const card = hostCard(msg("w", T1, { kind: "welcome", text: null }), crew(), info);
    expect(card).toEqual({
      text:
        "Bartek Z. zaczyna ekipę na to wydarzenie. Zbieramy do 4 osób, które idą razem. Na dobry początek: " +
        "Jaka jest Twoja ulubiona ulica lub budynek w Warszawie?",
      meetingPoint: "Punkt zbiórki: przy wejściu, Klub Jazzowy, ul. Mazowiecka 1",
      time: "Dziś, 19:00 · zbiórka 15 minut wcześniej",
    });
    expect(hostCard(msg("w", T1, { kind: "welcome", isMe: true }), crew(), info)?.text).toMatch(/^Zaczynasz ekipę/);
  });

  it("komplet: kategoria wydarzenia; bez miejsca i terminu - bez zmyślonych szczegółów", () => {
    const card = hostCard(msg("f", T1, { kind: "full", userId: null, name: null }), crew(), {
      category: "Sport",
      place: null,
      when: null,
    });
    expect(card).toEqual({
      text: "Mamy komplet 4 osób! Łączy Was kategoria „Sport”.",
      meetingPoint: "Punkt zbiórki: przy wejściu na miejsce wydarzenia",
      time: "Zbiórka 15 minut przed startem",
    });
  });

  it("wiadomość osoby i nieznany rodzaj nie są kartą", () => {
    expect(hostCard(msg("u", T1), crew(), info)).toBeNull();
    expect(hostCard(msg("x", T1, { kind: "poll" }), crew(), info)).toBeNull();
  });
});

describe("podpisy i podglądy", () => {
  it("podpis wiadomości: moje z „(Ty)”, bez imienia „Ktoś”", () => {
    expect(authorLabel({ name: "Ala N.", isMe: true })).toBe("Ala N. (Ty)");
    expect(authorLabel({ name: "Bartek Z.", isMe: false })).toBe("Bartek Z.");
    expect(authorLabel({ name: null, isMe: false })).toBe("Ktoś");
  });

  it("ostatnia wiadomość w jednej linii", () => {
    expect(messagePreview(msg("u", T1, { text: "Hej!" }))).toBe("Bartek Z.: Hej!");
    expect(messagePreview(msg("u", T1, { text: "Hej!", isMe: true }))).toBe("Ty: Hej!");
    expect(messagePreview(msg("w", T1, { kind: "welcome" }))).toBe(`${HOST}: ekipa wystartowała`);
    expect(messagePreview(msg("f", T1, { kind: "full" }))).toBe(`${HOST}: mamy komplet!`);
    expect(messagePreview(msg("j", T1, { kind: "joined" }))).toBe("Bartek Z. dołącza do ekipy");
    expect(messagePreview(msg("x", T1, { kind: "poll" }))).toBe("");
  });

  it("czas wiadomości po warszawsku: dziś sama godzina, inny dzień z datą", () => {
    const now = new Date("2026-10-18T19:00:00Z");
    expect(messageTime("2026-10-18T16:05:00.000Z", now)).toBe("18:05");
    expect(messageTime("2026-10-14T16:05:00.000Z", now)).toBe("14.10, 18:05");
    expect(messageTime("nie-data", now)).toBe("");
  });

  it("skład ekipy: ja pierwszy, potem pozostali w kolejności dołączania", () => {
    expect(otherNames(crew().members)).toEqual(["Bartek Z."]);
    expect(membersLine([])).toBe("Ty");
    expect(membersLine(["Bartek Z."])).toBe("Ty i Bartek Z.");
    expect(membersLine(["Piotr", "Kamil", "Antek"])).toBe("Ty, Piotr, Kamil i Antek");
    expect(crewSizeLabel(2, 4)).toBe("2/4 osoby");
  });

  it("nieprzeczytane z odmianą", () => {
    expect(unreadLabel(1)).toBe("1 nowa wiadomość");
    expect(unreadLabel(3)).toBe("3 nowe wiadomości");
    expect(unreadLabel(5)).toBe("5 nowych wiadomości");
  });
});

const mine = (eventId: string, over: Partial<MyCrew> = {}): MyCrew => ({
  eventId,
  title: `Wydarzenie ${eventId}`,
  crew: "001",
  capacity: 4,
  members: [],
  messageCount: 3,
  unread: 2,
  last: { kind: "user", userId: "u-2", name: "Bartek Z.", text: "Hej", sentAt: T1, isMe: false },
  ...over,
});
const list = (...items: MyCrew[]): MyCrews => ({ items, unread: items.reduce((s, c) => s + c.unread, 0) });

describe("plakietki: markCrewRead i arrivals", () => {
  it("otwarty czat zeruje swoją ekipę i sumę, bierze skład i ostatnią wiadomość z czatu", () => {
    const opened = crew({ messageCount: 4, messages: [msg("a", T1), msg("b", T3, { text: "Nowa" })] });
    const next = markCrewRead(list(mine("jazz"), mine("kino", { unread: 1 })), "jazz", opened);
    expect(next?.unread).toBe(1);
    const jazz = next?.items[0];
    expect(jazz?.unread).toBe(0);
    expect(jazz?.messageCount).toBe(4);
    expect(jazz?.members).toEqual(opened.members);
    expect(jazz?.last).toEqual({ kind: "user", userId: "u-2", name: "Bartek Z.", text: "Nowa", sentAt: T3, isMe: false });
  });

  it("ekipy spoza listy (pierwsze wejście) i brak danych - bez zmian", () => {
    const data = list(mine("kino"));
    expect(markCrewRead(data, "jazz", crew())).toBe(data);
    expect(markCrewRead(undefined, "jazz", crew())).toBeUndefined();
  });

  it("toast tylko, gdy przybyło cudzych nieprzeczytanych (nie przy pierwszym odczycie)", () => {
    const before = list(mine("jazz", { unread: 1 }), mine("kino", { unread: 0 }));
    expect(arrivals(undefined, before)).toEqual([]);
    const after = list(mine("jazz", { unread: 2 }), mine("kino", { unread: 0 }));
    expect(arrivals(before, after).map((c) => c.eventId)).toEqual(["jazz"]);
    expect(arrivals(after, after)).toEqual([]);
    const own = { kind: "user", userId: "u-1", name: "Ala N.", text: "Ja", sentAt: T3, isMe: true };
    expect(arrivals(after, list(mine("jazz", { unread: 3, last: own })))).toEqual([]);
  });
});
