import { createFileRoute, redirect } from "@tanstack/react-router";
import { z } from "zod";
import { LoginView } from "@/components/auth/login-view";
import { PageRouteError } from "@/components/layout/route-error";
import { afterLoginTarget } from "@/lib/login-redirect";

// redirect = ekran, na który ktoś wszedł bez sesji (np. link z QR „dodaj znajomego”); po logowaniu wracamy tam.
const LoginSearchSchema = z.object({ redirect: z.string().optional().catch(undefined) });

export const Route = createFileRoute("/login")({
  validateSearch: LoginSearchSchema,
  // Zalogowany nie musi logować się drugi raz: zapamiętany ekran albo strona główna (stamtąd ewentualnie do ankiety).
  beforeLoad: async ({ context, search }) => {
    if (await context.auth.hasSession()) throw redirect({ href: afterLoginTarget(search) });
  },
  component: LoginView,
  errorComponent: PageRouteError,
});
