import { useEffect, useRef, useState } from "react";
import { Icon } from "../../shared/Icon";
import { useToast } from "../../shared/toast";
import type { Answers, OnboardingField, OnboardingOption, OnboardingStep } from "../lib/types";
import { autoApply, isComplete, isFilled, isFull, isRequired, pick, values } from "../lib/wizard";

type Props = {
  step: OnboardingStep;
  index: number;
  total: number;
  answers: Answers;
  onApply: (stepAnswers: Answers) => void;
  onSkip: () => void;
  onClose: () => void;
};

// Okno pytania: karty odpowiedzi (ikona + etykieta) albo siatka przycisków dla długich list (dzielnice, wiek)
export function QuestionSheet({ step, index, total, answers, onApply, onSkip, onClose }: Props) {
  const toast = useToast();
  const [draft, setDraft] = useState<Answers>(() =>
    Object.fromEntries(step.fields.map((f) => [f.id, values(answers, f)]).filter(([, v]) => v.length)),
  );
  const dialogRef = useRef<HTMLDivElement>(null);
  const autoTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>("[aria-pressed]")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      window.clearTimeout(autoTimer.current);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  function choose(field: OnboardingField, option: OnboardingOption) {
    const result = pick(draft, field, option.id);
    if (result.limit) {
      toast(`Możesz wybrać maksymalnie ${result.limit}`);
      return;
    }
    setDraft(result.answers);
    if (autoApply(step)) {
      window.clearTimeout(autoTimer.current);
      autoTimer.current = window.setTimeout(() => onApply(result.answers), 260);
    }
  }

  const selected = step.fields.reduce((n, f) => n + values(draft, f).length, 0);
  const canFinish = isFilled(step, draft) && isComplete(step, draft);

  function finish() {
    if (!canFinish) {
      toast(isFilled(step, draft) ? "Uzupełnij wymagane pola" : "Wybierz co najmniej jedną opcję", "error");
      return;
    }
    onApply(draft);
  }

  return (
    <div className="sheet-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" ref={dialogRef}>
        <span className="sheet-handle" aria-hidden="true" />
        <div className="sheet-top">
          <span className="eyebrow">
            Kafelek {index + 1} z {total}
          </span>
          <button className="icon-btn icon-btn-round" type="button" onClick={onClose} aria-label="Zamknij">
            <Icon name="close" />
          </button>
        </div>
        <h2 id="sheet-title">{step.title}</h2>
        <p className="muted sheet-hint">{step.hint}</p>

        {step.fields.map((field) => {
          const chosen = values(draft, field);
          const asChips = field.type === "select" || field.options.every((o) => !o.icon);
          return (
            <div className="sheet-field" key={field.id}>
              {step.fields.length > 1 && field.label && (
                <h3>
                  {field.label}
                  {field.required && <span className="req"> *</span>}
                </h3>
              )}
              {asChips ? (
                <div className="chips">
                  {field.options.map((o) => (
                    <button key={o.id} type="button" className="chip-opt" aria-pressed={chosen.includes(o.id)} onClick={() => choose(field, o)}>
                      {o.label}
                    </button>
                  ))}
                </div>
              ) : (
                <div className={`opts${field.options.length > 3 ? " two-cols" : ""}`}>
                  {field.options.map((o) => {
                    const on = chosen.includes(o.id);
                    return (
                      <button
                        key={o.id}
                        type="button"
                        className={`opt${!on && isFull(draft, field) ? " dim" : ""}`}
                        aria-pressed={on}
                        onClick={() => choose(field, o)}
                      >
                        <span className="opt-icon">
                          <Icon name={o.icon ?? "radio_button_checked"} fill size={26} />
                        </span>
                        <span className="opt-label">{o.label}</span>
                        <Icon
                          className="opt-check"
                          name={on ? "check_circle" : field.type === "multi" ? "add_circle" : "radio_button_unchecked"}
                          fill
                          size={26}
                        />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        <div className="sheet-actions">
          {!isRequired(step) && (
            <button className="btn btn-outline btn-xl sheet-skip" type="button" onClick={onSkip}>
              Pomiń
            </button>
          )}
          <button className="btn btn-xl sheet-done" type="button" aria-disabled={!canFinish} onClick={finish}>
            {selected ? `Gotowe (${selected})` : "Gotowe"}
          </button>
        </div>
      </div>
    </div>
  );
}
