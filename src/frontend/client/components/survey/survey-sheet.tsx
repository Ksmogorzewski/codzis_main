import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import type { Answers, OnboardingField, OnboardingOption, OnboardingStep } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { autoApply, isFull, isRequired, pick, stepProblem, values, withText } from "@/lib/wizard";

type Props = {
  step: OnboardingStep;
  index: number;
  total: number;
  answers: Answers;
  onApply: (stepAnswers: Answers) => void;
  onSkip: () => void;
  onClose: () => void;
};

const focusRing =
  "outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card";

/** Długie listy bez ikon (dzielnice, wiek) jako pigułki, reszta jako karty z ikoną (mockup). */
const asChips = (field: OnboardingField) => field.type === "select" || field.options.every((o) => !o.icon);

function OptionCard({ field, option, on, dim, onPick }: OptionProps & { dim: boolean }) {
  const check = on ? "check_circle" : field.type === "multi" ? "add_circle" : "radio_button_unchecked";
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onPick(field, option)}
      className={cn(
        "flex min-h-[68px] items-center gap-3.5 rounded-xl border-2 bg-card px-3.5 py-3 text-left text-foreground transition-[background-color,border-color,opacity] duration-200 hover:border-input",
        focusRing,
        on && "border-primary bg-primary-soft hover:border-primary",
        dim && "opacity-45",
      )}
    >
      <span
        className={cn(
          "grid size-[46px] shrink-0 place-items-center rounded-[14px] bg-secondary text-primary-ink transition-colors duration-200",
          on && "bg-primary text-primary-foreground",
        )}
      >
        <Icon name={option.icon ?? "radio_button_checked"} size={26} filled />
      </span>
      <span className="flex-1 text-[17px] leading-[1.3] font-semibold">{option.label}</span>
      <Icon name={check} size={26} filled className={on ? "text-primary-ink" : "text-input"} />
    </button>
  );
}

type OptionProps = {
  field: OnboardingField;
  option: OnboardingOption;
  on: boolean;
  onPick: (field: OnboardingField, option: OnboardingOption) => void;
};

function OptionChip({ field, option, on, onPick }: OptionProps) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onPick(field, option)}
      className={cn(
        "inline-flex min-h-11 items-center rounded-full border-[1.5px] border-input bg-card px-4 text-base font-semibold text-foreground transition-[background-color,border-color,color] duration-200 hover:border-foreground",
        focusRing,
        on && "border-primary bg-primary text-primary-foreground hover:border-primary",
      )}
    >
      {option.label}
    </button>
  );
}

/** Wolny opis (pole „text”): kilka zdań, z podpowiedzią i licznikiem znaków. */
function TextAnswer({ field, value, onChange }: { field: OnboardingField; value: string; onChange: (text: string) => void }) {
  const hint = `${field.id}-podpowiedz`;
  const counter = `${field.id}-licznik`;
  const described = [field.hint && hint, field.maxLength && counter].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1.5">
      <Textarea
        aria-label={field.label}
        aria-describedby={described || undefined}
        rows={4}
        maxLength={field.maxLength}
        placeholder={field.placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex items-start justify-between gap-3 text-meta text-muted-foreground">
        {field.hint && <p id={hint}>{field.hint}</p>}
        {field.maxLength && (
          <p id={counter} className="ml-auto shrink-0">
            {value.length}/{field.maxLength}
          </p>
        )}
      </div>
    </div>
  );
}

/** Okno kafelka: pola kroku (single / multi z maxSelect / select / text), „Pomiń” dla opcjonalnych, „Gotowe”. */
export function SurveySheet({ step, index, total, answers, onApply, onSkip, onClose }: Props) {
  const [draft, setDraft] = useState<Answers>(() =>
    Object.fromEntries(step.fields.map((f) => [f.id, values(answers, f)]).filter(([, v]) => v.length > 0)),
  );
  const autoTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(autoTimer.current), []);

  function choose(field: OnboardingField, option: OnboardingOption) {
    const result = pick(draft, field, option.id);
    if (result.limit) {
      toast.info(`Możesz wybrać maksymalnie ${result.limit}`);
      return;
    }
    setDraft(result.answers);
    if (autoApply(step)) {
      clearTimeout(autoTimer.current);
      autoTimer.current = setTimeout(() => onApply(result.answers), 260);
    }
  }

  const selected = step.fields.reduce((n, f) => n + values(draft, f).length, 0);
  const problem = stepProblem(step, draft);

  function finish() {
    if (problem) toast.error(problem);
    else onApply(draft);
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="px-5 pt-2.5">
        <div aria-hidden="true" className="mb-2.5 h-[5px] w-11 self-center rounded-full bg-input" />
        <div className="flex min-h-11 items-center pr-14">
          <span className="text-meta font-bold tracking-[0.05em] text-brand-ink uppercase">
            Kafelek {index + 1} z {total}
            {!isRequired(step) && " · opcjonalny"}
          </span>
        </div>
        <SheetTitle className="mt-1 mb-1">{step.title}</SheetTitle>
        <SheetDescription className={cn("mb-4", !step.hint && "sr-only")}>
          {step.hint || step.title}
        </SheetDescription>

        <div className="flex flex-col gap-5">
          {step.fields.map((field) => {
            const chosen = values(draft, field);
            const full = isFull(draft, field);
            const showLabel = step.fields.length > 1 && field.label;
            return (
              <fieldset key={field.id} className="flex min-w-0 flex-col gap-2.5">
                <legend className={cn("mb-2.5 flex flex-wrap items-baseline gap-x-2", !showLabel && "sr-only")}>
                  <span className="text-lg font-bold">
                    {field.label ?? step.title}
                    {field.required && (
                      <span className="text-brand-ink" aria-hidden="true">
                        {" "}
                        *
                      </span>
                    )}
                  </span>
                  {field.required && <span className="sr-only">(wymagane)</span>}
                  {field.type === "multi" && field.maxSelect && (
                    <span className="text-meta text-muted-foreground">maks. {field.maxSelect}</span>
                  )}
                </legend>
                {field.type === "text" ? (
                  <TextAnswer
                    field={field}
                    value={chosen[0] ?? ""}
                    onChange={(text) => setDraft((d) => withText(d, field, text))}
                  />
                ) : asChips(field) ? (
                  <div className="flex flex-wrap gap-2">
                    {field.options.map((o) => (
                      <OptionChip key={o.id} field={field} option={o} on={chosen.includes(o.id)} onPick={choose} />
                    ))}
                  </div>
                ) : (
                  <div className={cn("grid gap-2.5", field.options.length > 3 && "md:grid-cols-2")}>
                    {field.options.map((o) => {
                      const on = chosen.includes(o.id);
                      return (
                        <OptionCard key={o.id} field={field} option={o} on={on} dim={full && !on} onPick={choose} />
                      );
                    })}
                  </div>
                )}
              </fieldset>
            );
          })}
        </div>

        <div className="sticky bottom-0 mt-1.5 flex gap-2.5 bg-card pt-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
          {!isRequired(step) && (
            <Button variant="outline" size="lg" className="flex-1" onClick={onSkip}>
              Pomiń
            </Button>
          )}
          <Button
            size="lg"
            variant={problem ? "secondary" : "default"}
            aria-disabled={problem !== null}
            className={cn("flex-[2]", problem && "text-muted-foreground")}
            onClick={finish}
          >
            {selected ? `Gotowe (${selected})` : "Gotowe"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
