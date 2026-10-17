import { createFileRoute } from "@tanstack/react-router";
import { GenericRouteError } from "@/components/layout/route-error";

// ZAŚLEPKA (faza A). Faza B: szczegóły z karty w cache ["recommendations", …], a bez cache -
// pobranie rekomendacji i wyszukanie po id; brak -> „Nie znaleziono”.
export const Route = createFileRoute("/_app/wydarzenie/$id")({
  component: EventPlaceholder,
  errorComponent: GenericRouteError,
});

function EventPlaceholder() {
  const { id } = Route.useParams();
  return <h1 className="text-[28px] font-extrabold tracking-[-0.02em]">Wydarzenie {id}</h1>;
}
