import { describe, expect, it } from "vitest";
import {
  AI_HOST,
  type ChatState,
  chatReducer,
  crewMembers,
  initialChat,
  memberNames,
  membersLine,
  ownLabel,
  timeline,
} from "./crew-chat";

const seed = [{ kind: "them" as const, author: "Kamil", text: "Cześć!" }];

describe("chatReducer", () => {
  it("start: czat zablokowany lodołamaczem, bez przycisku karty, nikt nie pisze, wiadomości z id", () => {
    const s = initialChat(seed);
    expect(s.locked).toBe(true);
    expect(s.beacon).toBe(false);
    expect(s.typing).toBeNull();
    expect(s.messages).toEqual([{ id: "m1", kind: "them", author: "Kamil", text: "Cześć!" }]);
  });

  it("pusta wiadomość nic nie zmienia", () => {
    const s = initialChat(seed);
    expect(chatReducer(s, { type: "send", text: "   ", author: "Ola (Ty)" })).toBe(s);
  });

  it("pierwsza odpowiedź odblokowuje czat; tekst przycięty, podpisany moim imieniem", () => {
    const s = chatReducer(initialChat(seed), { type: "send", text: "  Plac Zbawiciela ", author: "Ola (Ty)" });
    expect(s.locked).toBe(false);
    expect(s.messages.at(-1)).toEqual({ id: "m2", kind: "me", author: "Ola (Ty)", text: "Plac Zbawiciela" });
  });

  it("„pisze…” znika, gdy przychodzi wiadomość; przycisk karty koloru zostaje", () => {
    let s: ChatState = chatReducer(initialChat([]), { type: "typing", author: "Marta" });
    expect(s.typing).toBe("Marta");
    s = chatReducer(s, { type: "receive", message: { kind: "them", author: "Marta", text: "Hej" } });
    expect(s.typing).toBeNull();
    expect(s.beacon).toBe(false);
    s = chatReducer(s, { type: "receive", message: { kind: "them", author: "Kamil", text: "Jestem" }, beacon: true });
    s = chatReducer(s, { type: "receive", message: { kind: "them", author: "Antek", text: "Ok" } });
    expect(s.beacon).toBe(true);
    expect(s.messages.map((m) => m.id)).toEqual(["m1", "m2", "m3"]);
  });
});

describe("timeline", () => {
  const ai = { kind: "ai" as const, text: "Komplet", meetingPoint: "Wejście", time: "18:00" };
  const kamil = { kind: "them" as const, author: "Kamil", text: "Pasuje" };

  it("„X pisze…” na typingMs przed każdą wiadomością, czasy narastająco", () => {
    const t = timeline(
      [
        { afterMs: 1500, message: ai },
        { afterMs: 2000, message: kamil, beacon: true },
      ],
      1000,
    );
    expect(t).toEqual([
      { at: 500, action: { type: "typing", author: AI_HOST } },
      { at: 1500, action: { type: "receive", message: ai, beacon: undefined } },
      { at: 2500, action: { type: "typing", author: "Kamil" } },
      { at: 3500, action: { type: "receive", message: kamil, beacon: true } },
    ]);
  });

  it("krok krótszy niż pisanie: „pisze…” od razu po poprzedniej wiadomości", () => {
    const t = timeline([{ afterMs: 400, message: kamil }], 1000);
    expect(t.map((x) => x.at)).toEqual([0, 400]);
  });

  it("pusty scenariusz", () => {
    expect(timeline([])).toEqual([]);
  });
});

describe("crewMembers", () => {
  const demo = ["Kamil", "Marta", "Antek"];
  const demoMembers = [
    { userId: "demo-1", name: "Kamil" },
    { userId: "demo-2", name: "Marta" },
    { userId: "demo-3", name: "Antek" },
  ];

  it("bez listy zapisanych: osoby z demo ze stałymi id", () => {
    expect(crewMembers(undefined, demo, 3)).toEqual(demoMembers);
  });

  it("prawdziwi zapisani najpierw, bez mnie, bez pustych/„Ktoś” i powtórzeń osoby; reszta z demo", () => {
    const people = [
      { userId: "u1", name: "Ola", isMe: true },
      { userId: "u2", name: " Piotr ", isMe: false },
      { userId: "u3", name: null, isMe: false },
      { userId: "u4", name: "Ktoś", isMe: false },
      { userId: "u2", name: "Piotr", isMe: false },
      { userId: "u5", name: "Marta", isMe: false },
    ];
    expect(crewMembers(people, demo, 3)).toEqual([
      { userId: "u2", name: "Piotr" },
      { userId: "u5", name: "Marta" },
      { userId: "demo-1", name: "Kamil" },
    ]);
  });

  it("dwie zapisane „Ole” to dwie osoby w ekipie", () => {
    const people = [
      { userId: "u1", name: "Ola", isMe: false },
      { userId: "u2", name: "Ola", isMe: false },
    ];
    expect(crewMembers(people, demo, 3)).toEqual([
      { userId: "u1", name: "Ola" },
      { userId: "u2", name: "Ola" },
      { userId: "demo-1", name: "Kamil" },
    ]);
    expect(memberNames(crewMembers(people, demo, 3))).toEqual(["Ola", "Ola", "Kamil"]);
  });

  it("stary kontrakt bez userId: powtórzone imię to ta sama osoba", () => {
    const people = [
      { name: "Piotr", isMe: false },
      { name: "Piotr", isMe: false },
    ];
    expect(memberNames(crewMembers(people, demo, 3))).toEqual(["Piotr", "Kamil", "Marta"]);
  });

  it("więcej zapisanych niż miejsc: tylko pierwsi (najnowsi)", () => {
    const people = ["A", "B", "C", "D"].map((name) => ({ userId: name, name, isMe: false }));
    expect(memberNames(crewMembers(people, demo, 3))).toEqual(["A", "B", "C"]);
  });
});

describe("ownLabel", () => {
  it("imię z tokenu z dopiskiem, bez imienia „Ty”", () => {
    expect(ownLabel("Ola")).toBe("Ola (Ty)");
    expect(ownLabel(null)).toBe("Ty");
    expect(ownLabel("  ")).toBe("Ty");
  });
});

describe("membersLine", () => {
  it("ja pierwszy, ostatni po „i”", () => {
    expect(membersLine(["Piotr", "Kamil", "Antek"])).toBe("Ty, Piotr, Kamil i Antek");
    expect(membersLine(["Piotr"])).toBe("Ty i Piotr");
    expect(membersLine([])).toBe("Ty");
  });
});
