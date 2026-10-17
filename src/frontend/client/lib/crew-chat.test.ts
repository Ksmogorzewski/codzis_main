import { describe, expect, it } from "vitest";
import { chatReducer, initialChat } from "./crew-chat";

const seed = [{ kind: "them" as const, author: "Kamil", text: "Cześć!" }];

describe("crew-chat", () => {
  it("start: czat zablokowany lodołamaczem, bez przycisku karty, wiadomości z id", () => {
    const s = initialChat(seed);
    expect(s.locked).toBe(true);
    expect(s.beacon).toBe(false);
    expect(s.messages).toEqual([{ id: "m1", kind: "them", author: "Kamil", text: "Cześć!" }]);
  });

  it("pusta wiadomość nic nie zmienia", () => {
    const s = initialChat(seed);
    expect(chatReducer(s, { type: "send", text: "   " })).toBe(s);
  });

  it("pierwsza odpowiedź odblokowuje czat; tekst przycięty", () => {
    const s = chatReducer(initialChat(seed), { type: "send", text: "  Plac Zbawiciela " });
    expect(s.locked).toBe(false);
    expect(s.messages.at(-1)).toEqual({ id: "m2", kind: "me", text: "Plac Zbawiciela" });
  });

  it("wiadomości od ekipy i przycisk karty koloru", () => {
    let s = chatReducer(initialChat([]), { type: "receive", message: { kind: "them", author: "Marta", text: "Hej" } });
    expect(s.beacon).toBe(false);
    s = chatReducer(s, { type: "receive", message: { kind: "them", author: "Kamil", text: "Jestem" }, beacon: true });
    expect(s.beacon).toBe(true);
    expect(s.messages.map((m) => m.id)).toEqual(["m1", "m2"]);
  });
});
