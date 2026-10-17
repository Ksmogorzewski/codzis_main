import { describe, expect, it } from "vitest";
import type { OnboardingStep } from "./schemas";
import {
  autoApply,
  clearStep,
  filledCount,
  initialAnswers,
  isComplete,
  merge,
  missingRequired,
  pick,
  ready,
  sanitize,
  stepProblem,
  stepsWithErrors,
  summary,
} from "./wizard";

const opt = (id: string) => ({ id, label: id.toUpperCase(), icon: "star", short: `s-${id}` });
const STEPS: OnboardingStep[] = [
  { id: "who", icon: "group", title: "Z kim?", hint: "", fields: [{ id: "who", type: "single", required: true, options: [opt("solo"), opt("kids")] }] },
  { id: "vibe", icon: "mood", title: "Klimat", hint: "", fields: [{ id: "vibe", type: "multi", required: true, maxSelect: 2, options: [opt("a"), opt("b"), opt("c")] }] },
  {
    id: "where", icon: "near_me", title: "Gdzie?", hint: "",
    fields: [
      { id: "district", type: "select", required: true, options: [opt("wola"), opt("ochota")] },
      { id: "travel", type: "single", required: true, options: [opt("local"), opt("city")] },
    ],
  },
  { id: "city", icon: "location_city", title: "Miasto", hint: "", fields: [{ id: "city", type: "multi", required: false, options: [opt("eco"), opt("council")] }] },
];
const [who, vibe, where, city] = STEPS as [OnboardingStep, OnboardingStep, OnboardingStep, OnboardingStep];

describe("wizard", () => {
  it("single zastępuje odpowiedź, multi przełącza", () => {
    let a = pick({}, who.fields[0]!, "solo").answers;
    a = pick(a, who.fields[0]!, "kids").answers;
    expect(a.who).toEqual(["kids"]);
    a = pick(a, vibe.fields[0]!, "a").answers;
    a = pick(a, vibe.fields[0]!, "b").answers;
    a = pick(a, vibe.fields[0]!, "a").answers;
    expect(a.vibe).toEqual(["b"]);
  });

  it("multi pilnuje maxSelect", () => {
    const a = { vibe: ["a", "b"] };
    const r = pick(a, vibe.fields[0]!, "c");
    expect(r.limit).toBe(2);
    expect(r.answers).toBe(a);
  });

  it("wymagane kroki i gotowość do zapisu", () => {
    const partial = { who: ["solo"], vibe: ["a"], district: ["wola"] };
    expect(isComplete(where, partial)).toBe(false);
    expect(missingRequired(STEPS, partial).map((s) => s.id)).toEqual(["where"]);
    expect(ready(STEPS, { ...partial, travel: ["city"] })).toBe(true);
    expect(filledCount(STEPS, partial)).toBe(3);
  });

  it("sanitize usuwa nieznane pola/opcje i przycina do limitów", () => {
    expect(sanitize(STEPS, { who: ["kids", "solo"], vibe: ["a", "b", "c", "x"], old: ["1"], district: ["mars"] })).toEqual({
      who: ["kids"],
      vibe: ["a", "b"],
    });
    expect(sanitize(STEPS, null)).toEqual({});
  });

  it("merge i clearStep dotyczą tylko pól kroku", () => {
    const all = { who: ["solo"], city: ["eco"] };
    expect(merge(all, { city: ["council"] }, city)).toEqual({ who: ["solo"], city: ["council"] });
    expect(merge(all, {}, city)).toEqual({ who: ["solo"] });
    expect(clearStep(all, city)).toEqual({ who: ["solo"] });
  });

  it("krótkie etykiety i automatyczne zamykanie okna", () => {
    expect(summary(where, { district: ["wola"], travel: ["city"] })).toEqual(["s-wola", "s-city"]);
    expect([autoApply(who), autoApply(vibe), autoApply(where)]).toEqual([true, false, false]);
  });
});

describe("wizard: walidacja okna i błędy serwera", () => {
  it("okno kroku: nic nie wybrano / brak wymaganego pola / ok", () => {
    expect(stepProblem(who, {})).toBe("Wybierz co najmniej jedną opcję");
    expect(stepProblem(where, { district: ["wola"] })).toBe("Uzupełnij wymagane pola");
    expect(stepProblem(where, { district: ["wola"], travel: ["local"] })).toBeNull();
    // krok opcjonalny też wymaga wyboru w oknie (do pominięcia jest przycisk „Pomiń”)
    expect(stepProblem(city, {})).toBe("Wybierz co najmniej jedną opcję");
    expect(stepProblem(city, { city: ["eco"] })).toBeNull();
  });

  it("pola z błędem z serwera -> kafelki do poprawy", () => {
    expect([...stepsWithErrors(STEPS, ["travel", "vibe"])]).toEqual(["vibe", "where"]);
    expect(stepsWithErrors(STEPS, ["answers", "nieznane"]).size).toBe(0);
    expect(stepsWithErrors(STEPS, []).size).toBe(0);
  });

  it("odpowiedzi startowe: szkic ma pierwszeństwo przed zapisanym profilem, oba oczyszczone", () => {
    expect(initialAnswers(STEPS, { who: ["kids"], old: ["x"] }, { who: ["solo"] })).toEqual({ who: ["kids"] });
    expect(initialAnswers(STEPS, null, { who: ["solo"], vibe: ["a", "b", "c"] })).toEqual({ who: ["solo"], vibe: ["a", "b"] });
    expect(initialAnswers(STEPS, null, undefined)).toEqual({});
  });
});
