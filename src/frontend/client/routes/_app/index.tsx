import { createFileRoute } from "@tanstack/react-router";
import { GenericRouteError } from "@/components/layout/route-error";

// ZAŚLEPKA (faza A). Faza B: ekran główny 1a Karty - search params when/q (Zod), chipy kategorii,
// rekomendacje przez useRecommendations + withColdStartRetry.
export const Route = createFileRoute("/_app/")({
  component: HomePlaceholder,
  errorComponent: GenericRouteError,
});

function HomePlaceholder() {
  return <h1 className="text-[28px] font-extrabold tracking-[-0.02em]">Propozycje na dziś</h1>;
}
