import { createFileRoute, stripSearchParams } from "@tanstack/react-router";
import { GridSkeleton } from "@/components/events/card-skeleton";
import { ExploreView } from "@/components/explore/explore-view";
import { GenericRouteError } from "@/components/layout/route-error";
import { eventsQueryOptions } from "@/hooks/use-events.query";
import { onboardingQueryOptions } from "@/hooks/use-onboarding.query";
import { DEFAULT_EXPLORE, eventsParams, ExploreSearchSchema } from "@/lib/explore";

// Eksploruj: wszystkie wydarzenia w oknie czasu, filtry w adresie (domyślne nie zaśmiecają adresu).
// Listy nie blokujemy w loaderze: przy zmianie filtrów widok zostawia poprzednie karty (przygaszone).
export const Route = createFileRoute("/_app/eksploruj")({
  validateSearch: ExploreSearchSchema,
  search: { middlewares: [stripSearchParams(DEFAULT_EXPLORE)] },
  loaderDeps: ({ search }) => search,
  loader: ({ context, deps }) => {
    void context.queryClient.prefetchQuery(eventsQueryOptions(eventsParams(deps, new Date())));
    void context.queryClient.prefetchQuery(onboardingQueryOptions); // lista dzielnic
  },
  pendingComponent: () => <GridSkeleton />,
  component: ExploreView,
  errorComponent: GenericRouteError,
});
