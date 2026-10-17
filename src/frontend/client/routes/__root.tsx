import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, type ErrorComponentProps, Navigate, Outlet } from "@tanstack/react-router";
import { lazy, Suspense } from "react";
import { RouteError } from "@/components/layout/route-error";
import { Toaster } from "@/components/ui/sonner";
import type { RouterAuth } from "@/lib/auth";
import { CONFIG_ERROR, loadConfig } from "@/lib/config";

export type RouterContext = { queryClient: QueryClient; auth: RouterAuth };

// Devtools tylko w trybie dev i ładowane leniwie (nie trafiają do builda produkcyjnego).
const Devtools = import.meta.env.DEV ? lazy(() => import("../components/dev/devtools")) : () => null;

export const Route = createRootRouteWithContext<RouterContext>()({
  // Bez config.js (Cognito, adres API) nic nie zadziała - lepiej powiedzieć to od razu.
  beforeLoad: () => {
    const r = loadConfig();
    if (r.error !== null) throw new Error(r.error);
  },
  component: RootLayout,
  errorComponent: RootError,
  // Nieznany adres (np. stary #/rekomendacje): strona główna; strażnik ewentualnie przekieruje do logowania.
  notFoundComponent: () => <Navigate to="/" replace />,
});

function RootLayout() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <Outlet />
      <Toaster />
      <Suspense>
        <Devtools />
      </Suspense>
    </div>
  );
}

function RootError({ error, reset }: ErrorComponentProps) {
  const noConfig = error instanceof Error && error.message === CONFIG_ERROR;
  return (
    <main className="mx-auto w-full max-w-[1160px] px-4 pt-[18px] pb-10 md:px-8 md:pt-8">
      <RouteError message={noConfig ? CONFIG_ERROR : "Coś poszło nie tak"} onRetry={reset} />
    </main>
  );
}
