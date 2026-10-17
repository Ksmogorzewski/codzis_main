import { useCallback, useState } from "react";
import { Icon } from "../../shared/Icon";
import { plural } from "../../shared/format";
import { useToast } from "../../shared/toast";
import type { Answers, OnboardingStep } from "../lib/types";
import { clearStep, filledCount, isFilled, isRequired, merge, missingRequired, summary } from "../lib/wizard";
import { QuestionSheet } from "./QuestionSheet";

type Props = {
  steps: OnboardingStep[];
  answers: Answers;
  onChange: (answers: Answers) => void;
  onSave: () => Promise<void>;
  firstTime: boolean;
};

export function Survey({ steps, answers, onChange, onSave, firstTime }: Props) {
  const toast = useToast();
  const [open, setOpen] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const required = steps.filter(isRequired);
  const missing = missingRequired(steps, answers);
  const ready = missing.length === 0;
  const filled = filledCount(steps, answers);
  const close = useCallback(() => setOpen(null), []);

  async function save() {
    if (!ready) {
      toast(`Uzupełnij kafelki: ${missing.map((s) => steps.indexOf(s) + 1).join(", ")}`, "error");
      return;
    }
    setSaving(true);
    try {
      await onSave();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Nie udało się zapisać profilu", "error");
    } finally {
      setSaving(false);
    }
  }

  const step = open === null ? null : steps[open];

  return (
    <main className="page">
      <div className="page-head">
        <div className="eyebrow">Twój profil</div>
        <h1>Dopasujmy Warszawę do Ciebie</h1>
        <p className="lead">
          {firstTime
            ? `Odpowiedz na ${plural(required.length, "pytanie", "pytania", "pytań")} – resztę możesz pominąć. Zmienisz je w każdej chwili.`
            : "Zmień odpowiedzi, a dopasujemy propozycje do nowego profilu."}
        </p>
      </div>

      <div className="progress-block">
        <div className="progress-labels">
          <b>
            {filled}/{steps.length} wypełnione
          </b>
          <span>{ready ? "Gotowe do zapisania" : `Brakuje ${missing.length} z ${required.length} wymaganych`}</span>
        </div>
        <div className="progress">
          <div className="progress-bar" style={{ width: `${(filled / steps.length) * 100}%` }} />
        </div>
      </div>

      <div className="tiles">
        {steps.map((s, i) => {
          const done = isFilled(s, answers);
          return (
            <button key={s.id} type="button" className={`tile${done ? " filled" : ""}`} onClick={() => setOpen(i)}>
              <div className="tile-top">
                <span className="tile-icon">
                  <Icon name={s.icon} fill size={32} />
                </span>
                {done ? (
                  <span className="tile-check">
                    <Icon name="check" size={22} />
                  </span>
                ) : (
                  <span className="tile-num">{i + 1}</span>
                )}
              </div>
              <div className="tile-title">{s.title}</div>
              <div className="tile-foot">
                {done ? (
                  summary(s, answers).map((label) => (
                    <span className="chip-ok" key={label}>
                      {label}
                    </span>
                  ))
                ) : (
                  <span className="tile-state">
                    {skipped.has(s.id) ? "Pominięto · zmień" : isRequired(s) ? "Wybierz" : "Opcjonalne · wybierz"}
                    <Icon name="chevron_right" size={18} />
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div className="cta-block">
        <button className="btn btn-xl btn-cta" type="button" aria-disabled={!ready || saving} onClick={save}>
          {saving ? "Zapisywanie…" : "Zapisz i pokaż rekomendacje"}
          <Icon name="arrow_forward" />
        </button>
        {!ready && <span className="muted">Uzupełnij kafelki {missing.map((s) => steps.indexOf(s) + 1).join(", ")}, aby zapisać profil</span>}
      </div>

      {step && open !== null && (
        <QuestionSheet
          key={step.id}
          step={step}
          index={open}
          total={steps.length}
          answers={answers}
          onClose={close}
          onApply={(stepAnswers) => {
            onChange(merge(answers, stepAnswers, step));
            setSkipped((prev) => new Set([...prev].filter((id) => id !== step.id)));
            setOpen(null);
          }}
          onSkip={() => {
            onChange(clearStep(answers, step));
            setSkipped((prev) => new Set(prev).add(step.id));
            setOpen(null);
          }}
        />
      )}
    </main>
  );
}
