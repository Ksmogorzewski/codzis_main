import { createFileRoute, isRedirect, redirect, stripSearchParams } from "@tanstack/react-router";
import { HomeView } from "@/components/events/home-view";
import { GridSkeleton } from "@/components/events/card-skeleton";
import { GenericRouteError } from "@/components/layout/route-error";
import { meQueryOptions } from "@/hooks/use-me.query";
import { onboardingQueryOptions } from "@/hooks/use-onboarding.query";
import { onboardingRedirect } from "@/lib/onboarding-hint";
import { DEFAULT_SEARCH, HomeSearchSchema } from "@/lib/search";

// Ekran główny 1a Karty. Filtry w adresie (when, q, cat); domyślne wartości nie zaśmiecają adresu.
// Rekomendacji nie blokujemy w loaderze: zimny start trwa do ~30 s, więc widok pokazuje szkielet
// z komunikatem „Dobieramy propozycje…”.
export const Route = createFileRoute("/_app/")({
  validateSearch: HomeSearchSchema,
  search: { middlewares: [stripSearchParams(DEFAULT_SEARCH)] },
  loader: async ({ context }) => {
    void context.queryClient.prefetchQuery(onboardingQueryOptions);
    // Przywrócona sesja: jak po logowaniu, ankieta tylko dla konta bez profilu (nowe pytania = baner na ekranie).
    // Błąd /api/me nie blokuje ekranu.
    try {
      const me = await context.queryClient.ensureQueryData(meQueryOptions);
      const to = onboardingRedirect(me);
      if (to) throw redirect({ to });
    } catch (e) {
      if (isRedirect(e)) throw e;
    }
  },
  pendingComponent: () => <GridSkeleton />,
  component: HomeView,
  errorComponent: GenericRouteError,
});
