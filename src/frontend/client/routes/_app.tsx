import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Outlet, redirect, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { NameDialog } from "@/components/community/name-dialog";
import { Header } from "@/components/layout/header";
import { PageRouteError } from "@/components/layout/route-error";
import { TabBar } from "@/components/layout/tab-bar";
import { meQueryOptions } from "@/hooks/use-me.query";
import { currentName } from "@/lib/auth";
import { rememberTarget, requireSession, takeGoogleTarget } from "@/lib/login-redirect";
import { namePrompt, useNamePrompt } from "@/lib/name-prompt";
import { friendCodeRootKey, friendsGoingKey, friendsKey } from "@/lib/query-keys";
import { toggleDark, useDark } from "@/lib/theme";

// Pathless layout: strażnik logowania (bez sesji -> /login z powrotem na ten adres) + nagłówek wokół chronionych tras.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    await requireSession(context.auth, location.href);
    // Powrót z logowania Google: ekran z ?redirect=… (np. zaproszenie z QR) czekał w sessionStorage.
    // Nowe konto idzie najpierw do ankiety, a adres czeka na jej zapis - jak po logowaniu hasłem (auth-form.tsx).
    const target = takeGoogleTarget();
    if (!target) return;
    const me = await context.queryClient.fetchQuery(meQueryOptions).catch(() => null);
    if (me && (me.needsOnboarding || me.onboardingOutdated)) {
      rememberTarget(target);
      throw redirect({ to: "/profil" });
    }
    if (target !== location.href) throw redirect({ href: target });
  },
  component: AppLayout,
  errorComponent: PageRouteError,
});

function AppLayout() {
  const { auth, queryClient } = Route.useRouteContext();
  const navigate = Route.useNavigate();
  const dark = useDark();
  return (
    <>
      <Header
        dark={dark}
        onToggleDark={toggleDark}
        onLogout={async () => {
          await auth.signOut();
          queryClient.clear(); // dane poprzedniego użytkownika nie zostają w pamięci
          await navigate({ to: "/login" });
        }}
      />
      {/* Na telefonie miejsce na dolny pasek zakładek (56 px + bezpieczny obszar). */}
      <main className="mx-auto flex w-full max-w-[1160px] flex-col gap-4 px-4 pt-[18px] pb-[calc(96px+env(safe-area-inset-bottom))] md:px-8 md:pt-8 md:pb-16">
        <Outlet />
      </main>
      <TabBar />
      <RequiredName />
    </>
  );
}

/**
 * Konto bez imienia (sprzed 18.10) podaje je raz, zaraz po zalogowaniu - bez zamykania, bo znajomi muszą
 * wiedzieć, kogo dodają. To samo okno otwiera 409 name_required z tras znajomych (namePrompt).
 */
function RequiredName() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [missing, setMissing] = useState(() => currentName() === null);
  const asked = useNamePrompt();

  return (
    <NameDialog
      required
      open={missing || asked}
      onOpenChange={() => {}}
      onDone={() => {
        setMissing(false);
        namePrompt.close();
        // nowy token ma imię: trasy znajomych przestają odpowiadać 409
        void queryClient.invalidateQueries({ queryKey: friendsKey() });
        void queryClient.invalidateQueries({ queryKey: friendsGoingKey() });
        void queryClient.invalidateQueries({ queryKey: friendCodeRootKey() });
        void router.invalidate();
      }}
    />
  );
}
