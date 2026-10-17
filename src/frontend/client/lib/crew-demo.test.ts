import { describe, expect, it } from "vitest";
import { DEMO_CREW, demoScript, demoSeed } from "./crew-demo";

describe("crew-demo", () => {
  it("wiadomości startowe od członków ekipy; brakujące imiona z demo", () => {
    expect(demoSeed(["Piotr"]).map((m) => (m.kind === "ai" ? "" : m.author))).toEqual(["Piotr", "Marta", "Antek"]);
  });

  it("Wodzirej: punkt i termin zbiórki z danych wydarzenia, karta koloru na końcu", () => {
    const script = demoScript({ members: DEMO_CREW.names, category: "Kultura", place: "Teatr Studio", when: "Dziś, 19:00" });
    const ai = script.find((s) => s.message.kind === "ai")?.message;
    expect(ai).toMatchObject({
      text: "Mamy komplet 4 osób! Łączy Was kategoria „Kultura”.",
      meetingPoint: "Punkt zbiórki: przy wejściu, Teatr Studio",
      time: "Dziś, 19:00 · zbiórka 15 minut wcześniej",
    });
    expect(script.at(-1)?.beacon).toBe(true);
    expect(script.every((s) => s.afterMs > 0)).toBe(true);
  });

  it("bez miejsca i terminu: bez zmyślonych danych", () => {
    const ai = demoScript({ members: [], category: "Sport", place: null, when: null }).find(
      (s) => s.message.kind === "ai",
    )?.message;
    expect(ai).toMatchObject({
      meetingPoint: "Punkt zbiórki: przy wejściu na miejsce wydarzenia",
      time: "Zbiórka 15 minut przed startem",
    });
  });
});
