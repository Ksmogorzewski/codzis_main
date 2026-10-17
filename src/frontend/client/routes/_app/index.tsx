import { createFileRoute, isRedirect, redirect, stripSearchParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { HomeView } from "@/components/events/home-view";
import { GenericRouteError } from "@/components/layout/route-error";
import { meQueryOptions } from "@/hooks/use-me.query";
import { onboardingQueryOptions } from "@/hooks/use-onboarding.query";
import { DEFAULT_SEARCH, HomeSearchSchema } from "@/lib/search";

// Ekran główny 1a Karty. Filtry w adresie (when, q, cat); domyślne wartości nie zaśmiecają adresu.
// Rekomendacji nie blokujemy w loaderze: zimny start trwa do ~30 s, więc widok pokazuje szkielet
// z komunikatem „Dobieramy propozycje…”.
export const Route = createFileRoute("/_app/")({
  validateSearch: HomeSearchSchema,
  search: { middlewares: [stripSearchParams(DEFAULT_SEARCH)] },
  loader: async ({ context }) => {
    void context.queryClient.prefetchQuery(onboardingQueryOptions);
    // Przywrócona sesja: jak po logowaniu, profil decyduje o ankiecie. Błąd /api/me nie blokuje ekranu.
    try {
      const me = await context.queryClient.ensureQueryData(meQueryOptions);
      if (me.needsOnboarding) throw redirect({ to: "/profil" });
      if (me.onboardingOutdated) {
        toast("Dodaliśmy nowe pytania – uzupełnij profil.");
        throw redirect({ to: "/profil" });
      }
    } catch (e) {
      if (isRedirect(e)) throw e;
    }
  },
  component: HomeView,
  errorComponent: GenericRouteError,
});
