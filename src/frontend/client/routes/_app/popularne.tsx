import { createFileRoute } from "@tanstack/react-router";
import { GridSkeleton } from "@/components/events/card-skeleton";
import { DataRouteError } from "@/components/layout/route-error";
import { PopularView } from "@/components/popular/popular-view";
import { popularQueryOptions } from "@/hooks/use-popular.query";

// Popularne w najbliższym tygodniu (GET /api/popular): jedno zapytanie bez parametrów, więc czekamy na nie w loaderze.
export const Route = createFileRoute("/_app/popularne")({
  loader: ({ context }) => context.queryClient.ensureQueryData(popularQueryOptions),
  pendingComponent: () => <GridSkeleton />,
  errorComponent: DataRouteError,
  component: PopularView,
});
