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

// Pole tekstowe: odpowiedź to [tekst] przycięty do maxLength; same spacje = brak odpowiedzi
export function withText(answers: Answers, field: OnboardingField, text: string): Answers {
  const out = { ...answers };
  if (text.trim()) out[field.id] = [field.maxLength ? text.slice(0, field.maxLength) : text];
  else delete out[field.id];
  return out;
}

// Ile znaków wolnego opisu mieści się na kafelku
export const TEXT_CHIP_CHARS = 28;
const shorten = (text: string) => {
  const line = text.split(/\s+/).filter(Boolean).join(" ");
  return line.length > TEXT_CHIP_CHARS ? `${line.slice(0, TEXT_CHIP_CHARS - 1).trimEnd()}…` : line;
};

// Krótkie etykiety wybranych opcji (kafelek, podsumowanie profilu); wolny opis - jego początek
export const summary = (step: OnboardingStep, answers: Answers) =>
  step.fields.flatMap((f) =>
    f.type === "text"
      ? values(answers, f).map(shorten)
      : values(answers, f)
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
      if (f.type === "text") {
        const text = (answers?.[f.id]?.[0] ?? "").trim();
        if (text) out[f.id] = [f.maxLength ? text.slice(0, f.maxLength) : text];
        continue;
      }
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
export const autoApply = (step: OnboardingStep) =>
  step.fields.length === 1 && step.fields[0]!.type !== "multi" && step.fields[0]!.type !== "text";

// Okno kroku: komunikat, gdy nie da się go zatwierdzić „Gotowe” (null = można).
export function stepProblem(step: OnboardingStep, draft: Answers): string | null {
  if (!isFilled(step, draft))
    return step.fields.some((f) => f.type === "text") ? "Uzupełnij co najmniej jedno pole" : "Wybierz co najmniej jedną opcję";
  if (!isComplete(step, draft)) return "Uzupełnij wymagane pola";
  return null;
}

// Pola z błędem z odpowiedzi 400 PUT /api/profile ({fields}) -> id kafelków do poprawy
export function stepsWithErrors(steps: OnboardingStep[], fields: readonly string[]): Set<string> {
  const bad = new Set(fields);
  return new Set(steps.filter((s) => s.fields.some((f) => bad.has(f.id))).map((s) => s.id));
}

// Start ankiety: niezapisany szkic z localStorage, a bez niego zapisany profil
export const initialAnswers = (steps: OnboardingStep[], draft: Answers | null, saved: Answers | null | undefined) =>
  sanitize(steps, draft ?? saved);

// Klucz szkicu w localStorage (jak u nich: osobny dla każdego użytkownika)
export const draftKey = (userId: string) => `warsawnow-draft-${userId}`;
