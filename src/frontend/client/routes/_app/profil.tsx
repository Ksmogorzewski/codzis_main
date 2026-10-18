import { createFileRoute } from "@tanstack/react-router";
import { AccountCard } from "@/components/account/account-card";
import { DataRouteError } from "@/components/layout/route-error";
import { SurveySkeleton } from "@/components/survey/survey-skeleton";
import { SurveyView } from "@/components/survey/survey-view";
import { meQueryOptions, useMe } from "@/hooks/use-me.query";
import { onboardingQueryOptions } from "@/hooks/use-onboarding.query";

// Profil: dane konta (zdjęcie, imię, nazwisko, data urodzenia) i ankieta - pytania (GET /api/onboarding)
// i zapisane odpowiedzi (GET /api/me) przed renderem.
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
  // Dane konta z cache (zapis i zdjęcie aktualizują je przez setQueryData), ankieta z danych loadera.
  const live = useMe().data ?? me;
  return (
    <>
      <AccountCard key={live.userId} me={live} />
      {/* key: inny użytkownik, nowa wersja pytań albo nowo zapisany profil = świeży stan ankiety
          (po powrocie na Profil router najpierw pokazuje dane loadera z poprzedniej wizyty, potem je odświeża) */}
      <SurveyView key={`${me.userId}:${steps.length}:${me.profile?.completedAt ?? ""}`} me={me} steps={steps} />
    </>
  );
}
