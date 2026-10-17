import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useSaveProfile } from "@/hooks/use-save-profile.mutation";
import { ApiRequestError } from "@/lib/api";
import { type Answers, AnswersSchema, type Me, type OnboardingStep } from "@/lib/schemas";
import { lastSearch } from "@/lib/search";
import { readJson, writeJson } from "@/lib/storage";
import { cn } from "@/lib/utils";
import {
  clearStep,
  draftKey,
  filledCount,
  initialAnswers,
  isFilled,
  isRequired,
  merge,
  missingRequired,
  stepsWithErrors,
  summary,
} from "@/lib/wizard";
import { plural } from "../../../shared/format";
import { SurveySheet } from "./survey-sheet";

type Props = { me: Me; steps: OnboardingStep[] };

const MAX_TILE_CHIPS = 3;

function tileState(step: OnboardingStep, skipped: boolean): string {
  if (skipped) return "Pominięto · zmień";
  return isRequired(step) ? "Wybierz" : "Opcjonalne · wybierz";
}

/** Szkic z localStorage; uszkodzony albo w starym kształcie jest ignorowany. */
function readDraft(key: string): Answers | null {
  const parsed = AnswersSchema.safeParse(readJson<unknown>("local", key));
  return parsed.success ? parsed.data : null;
}

/** Ankieta profilu: kafelki z GET /api/onboarding, okno pytania, zapis PUT /api/profile. */
export function SurveyView({ me, steps }: Props) {
  const navigate = useNavigate();
  const save = useSaveProfile();
  const key = draftKey(me.userId);
  // Niezapisane odpowiedzi przetrwają przeładowanie strony (localStorage, jak w ich App.tsx).
  const [answers, setAnswersState] = useState<Answers>(() =>
    initialAnswers(steps, readDraft(key), me.profile?.answers),
  );
  const [open, setOpen] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<Set<string>>(() => new Set());
  const [invalid, setInvalid] = useState<Set<string>>(() => new Set());

  const required = steps.filter(isRequired);
  const missing = missingRequired(steps, answers);
  const ready = missing.length === 0;
  const filled = filledCount(steps, answers);
  const missingNumbers = missing.map((s) => steps.indexOf(s) + 1).join(", ");
  const firstTime = me.needsOnboarding;

  function setAnswers(next: Answers) {
    setAnswersState(next);
    writeJson("local", key, next);
  }

  function updateStep(step: OnboardingStep, next: Answers, wasSkipped: boolean) {
    setAnswers(next);
    setSkipped((prev) => {
      const out = new Set(prev);
      if (wasSkipped) out.add(step.id);
      else out.delete(step.id);
      return out;
    });
    setInvalid((prev) => new Set([...prev].filter((id) => id !== step.id)));
    setOpen(null);
  }

  function submit() {
    if (!ready) {
      toast.error(`Uzupełnij kafelki: ${missingNumbers}`);
      return;
    }
    save.mutate(answers, {
      onSuccess: () => {
        writeJson("local", key, null);
        toast.success("Profil zapisany");
        void navigate({ to: "/", search: lastSearch() });
      },
      onError: (error) => {
        // 401 i 409 obsługuje globalny onError (main.tsx); tu błędy walidacji i serwera.
        if (error instanceof ApiRequestError && error.fields.length > 0) {
          setInvalid(stepsWithErrors(steps, error.fields));
        }
        toast.error(error instanceof ApiRequestError ? error.message : "Nie udało się zapisać profilu");
      },
    });
  }

  const step = open === null ? null : steps[open];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="text-meta font-bold tracking-[0.04em] text-brand-ink uppercase">Twój profil</p>
        <h1 className="text-3xl leading-[1.1] font-extrabold tracking-[-0.03em] text-balance md:text-[42px]">
          Dopasujmy Warszawę do Ciebie
        </h1>
        <p className="text-[17px] leading-[1.45] text-muted-foreground">
          {firstTime
            ? `Odpowiedz na ${plural(required.length, "pytanie", "pytania", "pytań")} – resztę możesz pominąć. Zmienisz je w każdej chwili.`
            : "Zmień odpowiedzi, a dopasujemy propozycje do nowego profilu."}
        </p>
      </header>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-base font-bold">
          <span>
            {filled}/{steps.length} wypełnione
          </span>
          <span className="font-medium text-muted-foreground">
            {ready ? "Gotowe do zapisania" : `Brakuje ${missing.length} z ${required.length} wymaganych`}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Wypełnione kafelki"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={filled}
          className="h-3 overflow-hidden rounded-full bg-secondary"
        >
          <div
            className="h-full rounded-full bg-success transition-[width] duration-[250ms] ease-[cubic-bezier(.2,.8,.2,1)]"
            style={{ width: `${steps.length ? (filled / steps.length) * 100 : 0}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {steps.map((s, i) => {
          const done = isFilled(s, answers);
          const bad = invalid.has(s.id);
          const chips = summary(s, answers);
          return (
            <button
              type="button"
              key={s.id}
              onClick={() => setOpen(i)}
              className={cn(
                "flex min-h-[190px] flex-col gap-3 rounded-2xl border-2 bg-card p-4 text-left text-foreground outline-none transition-[border-color,transform] duration-200 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-safe:hover:-translate-y-0.5 motion-safe:active:scale-[.98] md:min-h-[220px]",
                done && "border-success",
                bad && "border-brand",
              )}
            >
              <span className="flex items-start justify-between">
                <span className="grid size-14 place-items-center rounded-xl bg-primary-soft text-primary-ink">
                  <Icon name={s.icon} size={32} filled />
                </span>
                {bad ? (
                  <span className="grid size-8 place-items-center rounded-full bg-brand text-brand-foreground">
                    <Icon name="priority_high" size={20} />
                  </span>
                ) : done ? (
                  <span className="grid size-8 place-items-center rounded-full bg-success text-primary-foreground motion-safe:animate-pop">
                    <Icon name="check" size={22} />
                  </span>
                ) : (
                  <span className="grid size-8 place-items-center rounded-full border-2 border-input text-meta font-bold text-muted-foreground">
                    {i + 1}
                  </span>
                )}
              </span>
              <span className="text-[17px] leading-tight font-bold text-pretty md:text-title">
                {s.title}
                {isRequired(s) && !done && (
                  <>
                    <span className="text-brand-ink" aria-hidden="true">
                      {" "}
                      *
                    </span>
                    <span className="sr-only"> (wymagane)</span>
                  </>
                )}
              </span>
              <span className="mt-auto flex flex-wrap gap-1.5">
                {bad && <span className="text-meta font-semibold text-brand-ink">Popraw odpowiedź</span>}
                {!bad &&
                  done &&
                  chips.slice(0, MAX_TILE_CHIPS).map((label) => (
                    <Badge key={label} variant="success" className="text-sm">
                      {label}
                    </Badge>
                  ))}
                {!bad && done && chips.length > MAX_TILE_CHIPS && (
                  <Badge variant="secondary" className="text-sm">
                    +{chips.length - MAX_TILE_CHIPS}
                  </Badge>
                )}
                {!bad && !done && (
                  <span className="flex items-center gap-0.5 text-meta font-semibold text-muted-foreground">
                    {tileState(s, skipped.has(s.id))}
                    <Icon name="chevron_right" size={18} />
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-meta text-muted-foreground">
        <span className="text-brand-ink" aria-hidden="true">
          *
        </span>{" "}
        – wymagane
      </p>

      <div className="flex flex-col items-stretch gap-2.5 md:items-start">
        <Button
          size="xl"
          variant={ready ? "brand" : "secondary"}
          aria-disabled={!ready}
          disabled={save.isPending}
          aria-busy={save.isPending}
          onClick={submit}
          // na wąskim telefonie tekst może się zawinąć zamiast wyjść poza przycisk
          className={cn("h-auto min-h-[60px] py-3 text-center whitespace-normal", !ready && "text-muted-foreground hover:bg-secondary")}
        >
          {save.isPending ? "Zapisuję…" : "Zapisz i pokaż rekomendacje"}
          {!save.isPending && <Icon name="arrow_forward" size={22} />}
        </Button>
        {!ready && (
          <span className="text-meta text-muted-foreground">Uzupełnij kafelki {missingNumbers}, aby zapisać profil</span>
        )}
      </div>

      {step && open !== null && (
        <SurveySheet
          key={step.id}
          step={step}
          index={open}
          total={steps.length}
          answers={answers}
          onClose={() => setOpen(null)}
          onApply={(stepAnswers) => updateStep(step, merge(answers, stepAnswers, step), false)}
          onSkip={() => updateStep(step, clearStep(answers, step), true)}
        />
      )}
    </div>
  );
}
