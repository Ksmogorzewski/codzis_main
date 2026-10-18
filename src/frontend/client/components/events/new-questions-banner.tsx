import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useMe } from "@/hooks/use-me.query";
import { useOnboarding } from "@/hooks/use-onboarding.query";
import { dismissNewQuestions, isDismissed, showNewQuestions } from "@/lib/onboarding-hint";

/**
 * Doszło wymagane pytanie, a profil jest już wypełniony: prośba o uzupełnienie bez wymuszania ankiety.
 * „Później” ukrywa baner dla tej wersji pytań (lib/onboarding-hint.ts).
 */
export function NewQuestionsBanner() {
  const me = useMe().data;
  const version = useOnboarding().data?.version;
  // ukryte w tej karcie (działa też bez localStorage) + zapamiętane wcześniej
  const [hidden, setHidden] = useState<readonly string[]>([]);
  const dismissed = new Set(version && isDismissed(version) ? [...hidden, version] : hidden);
  if (!version || !showNewQuestions(me, version, dismissed)) return null;

  return (
    <section
      aria-label="Nowe pytania w profilu"
      className="flex flex-col gap-3 border-2 border-input bg-card px-4 py-3 text-card-foreground sm:flex-row sm:items-center"
    >
      <p className="flex flex-1 items-start gap-3 text-base">
        <Icon name="tune" size={22} className="mt-px text-brand-ink" />
        Mamy nowe pytania w profilu — uzupełnij, żeby lepiej dopasować propozycje.
      </p>
      <div className="flex gap-2 self-end sm:self-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            dismissNewQuestions(version);
            setHidden((prev) => [...prev, version]);
          }}
        >
          Później
        </Button>
        <Button asChild size="sm">
          <Link to="/profil">Uzupełnij</Link>
        </Button>
      </div>
    </section>
  );
}
