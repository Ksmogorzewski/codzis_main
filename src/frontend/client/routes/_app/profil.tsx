import { createFileRoute } from "@tanstack/react-router";
import { useEffect } from "react";
import { toast } from "sonner";
import { DataRouteError } from "@/components/layout/route-error";
import { SurveySkeleton } from "@/components/survey/survey-skeleton";
import { SurveyView } from "@/components/survey/survey-view";
import { meQueryOptions } from "@/hooks/use-me.query";
import { onboardingQueryOptions } from "@/hooks/use-onboarding.query";

// Ankieta profilu: pytania (GET /api/onboarding) i zapisane odpowiedzi (GET /api/me) przed renderem.
export const Route = createFileRoute("/_app/profil")({
  loader: async ({ context }) => {
    const [me, onboarding] = await Promise.all([
      context.queryClient.ensureQueryData(meQueryOptions),
      context.queryClient.ensureQueryData(onboardingQueryOptions),
    ]);
    return { me, steps: onboarding.steps };
  },
  pendingComponent: SurveySkeleton,
  errorComponent: DataRouteError,
  component: ProfilePage,
});

function ProfilePage() {
  const { me, steps } = Route.useLoaderData();
  // Wpadliśmy tu z ekranu głównego, bo doszły nowe pytania (id: bez dublowania przy ponownym wejściu).
  useEffect(() => {
    if (me.onboardingOutdated && !me.needsOnboarding) toast("Dodaliśmy nowe pytania – uzupełnij profil.", { id: "onboarding-outdated" });
  }, [me.onboardingOutdated, me.needsOnboarding]);
  // key: inny użytkownik albo nowa wersja pytań = świeży stan ankiety
  return <SurveyView key={`${me.userId}:${steps.length}`} me={me} steps={steps} />;
}
