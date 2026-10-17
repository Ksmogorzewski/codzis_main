import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { Header } from "@/components/layout/header";
import { PageRouteError } from "@/components/layout/route-error";
import { TabBar } from "@/components/layout/tab-bar";
import { toggleDark, useDark } from "@/lib/theme";

// Pathless layout: strażnik logowania + nagłówek wokół chronionych tras.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    if (!(await context.auth.hasSession())) throw redirect({ to: "/login" });
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
    </>
  );
}
