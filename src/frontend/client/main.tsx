import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createHashHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ApiRequestError, isNameRequired, isNeedsOnboarding, shouldRetry } from "./lib/api";
import { routerAuth } from "./lib/auth";
import { namePrompt } from "./lib/name-prompt";
import { routeTree } from "./routeTree.gen";
import "./styles.css";

// Błędy z dowolnego zapytania lub mutacji, które zmieniają ekran:
//   401 (sesja wygasła i nie dało się jej odświeżyć) -> logowanie,
//   409 / code "needs_onboarding" -> ankieta profilu,
//   409 / code "name_required" (trasy znajomych, konto bez imienia) -> prośba o imię (NameDialog w _app.tsx).
const onError = (error: unknown) => {
  if (error instanceof ApiRequestError && error.status === 401) {
    void routerAuth.signOut();
    queryClient.clear();
    // po ponownym zalogowaniu powrót na bieżący ekran (lib/login-redirect.ts)
    const href = router.state.location.href;
    void router.navigate({ to: "/login", search: href && href !== "/" ? { redirect: href } : {} });
  } else if (isNeedsOnboarding(error)) {
    void router.navigate({ to: "/profil" });
  } else if (isNameRequired(error)) {
    namePrompt.open();
  }
};

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    // Ponawiamy tylko błędy przejściowe (sieć, 5xx); 4xx od razu trafiają do UI.
    queries: { staleTime: 30_000, retry: shouldRetry, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});

// Routing na "#": CloudFront przed S3 nie ma fallbacku SPA dla głębokich linków.
const router = createRouter({
  routeTree,
  history: createHashHistory(),
  context: { queryClient, auth: routerAuth },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  defaultPendingMs: 150,
  defaultPendingMinMs: 250,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const el = document.getElementById("root");
if (el) {
  createRoot(el).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
