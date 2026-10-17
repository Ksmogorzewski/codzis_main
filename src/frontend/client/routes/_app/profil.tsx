import { createFileRoute } from "@tanstack/react-router";
import { GenericRouteError } from "@/components/layout/route-error";

// ZAŚLEPKA (faza A). Faza B: ankieta z GET /api/onboarding (kafelki + Sheet), zapis PUT /api/profile.
export const Route = createFileRoute("/_app/profil")({
  component: ProfilePlaceholder,
  errorComponent: GenericRouteError,
});

function ProfilePlaceholder() {
  return <h1 className="text-[28px] font-extrabold tracking-[-0.02em]">Twój profil</h1>;
}
