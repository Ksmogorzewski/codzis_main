// Logika kafelków profilu, bez DOM. Kroki i pola przychodzą z GET /api/onboarding.
import type { Answers, OnboardingField, OnboardingStep } from "./schemas";

export const values = (answers: Answers, field: OnboardingField) => answers[field.id] ?? [];
export const isRequired = (step: OnboardingStep) => step.fields.some((f) => f.required);
export const isFilled = (step: OnboardingStep, answers: Answers) => step.fields.some((f) => values(answers, f).length > 0);
export const isComplete = (step: OnboardingStep, answers: Answers) =>
  step.fields.every((f) => !f.required || values(answers, f).length > 0);

// single/select: zastępuje; multi: przełącza z limitem maxSelect (limit = osiągnięto limit, bez zmiany)
export function pick(answers: Answers, field: OnboardingField, optionId: string): { answers: Answers; limit?: number } {
  const current = values(answers, field);
  if (field.type !== "multi") return { answers: { ...answers, [field.id]: [optionId] } };
  if (current.includes(optionId)) return { answers: { ...answers, [field.id]: current.filter((v) => v !== optionId) } };
  if (field.maxSelect && current.length >= field.maxSelect) return { answers, limit: field.maxSelect };
  return { answers: { ...answers, [field.id]: [...current, optionId] } };
}

export const isFull = (answers: Answers, field: OnboardingField) =>
  field.type === "multi" && !!field.maxSelect && values(answers, field).length >= field.maxSelect;

// Krótkie etykiety wybranych opcji (kafelek, podsumowanie profilu)
export const summary = (step: OnboardingStep, answers: Answers) =>
  step.fields.flatMap((f) =>
    values(answers, f)
      .map((id) => f.options.find((o) => o.id === id)?.short)
      .filter((s): s is string => Boolean(s)),
  );

export const filledCount = (steps: OnboardingStep[], answers: Answers) => steps.filter((s) => isFilled(s, answers)).length;
export const missingRequired = (steps: OnboardingStep[], answers: Answers) =>
  steps.filter((s) => isRequired(s) && !isComplete(s, answers));
export const ready = (steps: OnboardingStep[], answers: Answers) => missingRequired(steps, answers).length === 0;

// Usuwa odpowiedzi do pól/opcji, których już nie ma (pytania się zmieniły) i przycina do limitów
export function sanitize(steps: OnboardingStep[], answers: Answers | null | undefined): Answers {
  const out: Answers = {};
  for (const step of steps) {
    for (const f of step.fields) {
      const ids = new Set(f.options.map((o) => o.id));
      const v = [...new Set((answers?.[f.id] ?? []).filter((x) => ids.has(x)))];
      const limited = f.type === "multi" ? (f.maxSelect ? v.slice(0, f.maxSelect) : v) : v.slice(0, 1);
      if (limited.length) out[f.id] = limited;
    }
  }
  return out;
}

// Odpowiedzi jednego kroku (szkic z okna) -> do wszystkich odpowiedzi
export function merge(answers: Answers, stepAnswers: Answers, step: OnboardingStep): Answers {
  const out = { ...answers };
  for (const f of step.fields) {
    const v = stepAnswers[f.id] ?? [];
    if (v.length) out[f.id] = v;
    else delete out[f.id];
  }
  return out;
}

export function clearStep(answers: Answers, step: OnboardingStep): Answers {
  const out = { ...answers };
  step.fields.forEach((f) => delete out[f.id]);
  return out;
}

// Okno z jednym polem jednokrotnego wyboru zamyka się samo po kliknięciu (jak w makiecie)
export const autoApply = (step: OnboardingStep) => step.fields.length === 1 && step.fields[0]!.type !== "multi";
