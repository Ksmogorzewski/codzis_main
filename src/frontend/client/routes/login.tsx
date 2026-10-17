import { createFileRoute, redirect } from "@tanstack/react-router";
import { LoginView } from "@/components/auth/login-view";
import { PageRouteError } from "@/components/layout/route-error";

export const Route = createFileRoute("/login")({
  // Zalogowany nie musi logować się drugi raz: strona główna (stamtąd ewentualnie do ankiety).
  beforeLoad: async ({ context }) => {
    if (await context.auth.hasSession()) throw redirect({ to: "/" });
  },
  component: LoginView,
  errorComponent: PageRouteError,
});
