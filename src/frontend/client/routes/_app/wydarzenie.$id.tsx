import { createFileRoute } from "@tanstack/react-router";
import { EventDetailView } from "@/components/events/event-detail";
import { GenericRouteError } from "@/components/layout/route-error";

// Szczegóły z karty w cache rekomendacji; po odświeżeniu strony widok sam pobiera listę i szuka po id
// (hooks/use-event-card.query.ts). Bez loadera, bo zimny start rekomendacji trwa do ~30 s.
export const Route = createFileRoute("/_app/wydarzenie/$id")({
  component: EventDetailView,
  errorComponent: GenericRouteError,
});
