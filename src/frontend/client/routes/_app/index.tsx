import { createFileRoute, stripSearchParams } from "@tanstack/react-router";
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
  loader: ({ context }) => {
    // podsumowanie profilu w nagłówku – nie blokuje ekranu
    void context.queryClient.prefetchQuery(meQueryOptions);
    void context.queryClient.prefetchQuery(onboardingQueryOptions);
  },
  component: HomeView,
  errorComponent: GenericRouteError,
});
