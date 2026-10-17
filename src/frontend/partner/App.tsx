import { useCallback, useEffect, useState } from "react";
import { useToast } from "../shared/toast";
import { navigate, useHashRoute } from "../shared/useHashRoute";
import { EventForm } from "./components/EventForm";
import { Events } from "./components/Events";
import { Login } from "./components/Login";
import { Payments } from "./components/Payments";
import { Sidebar } from "./components/Sidebar";
import { ApiError, api } from "./lib/api";
import { session } from "./lib/session";
import type { Profile } from "./lib/types";

export type Screen = "wydarzenia" | "dodaj" | "platnosci";
const SCREENS: Screen[] = ["wydarzenia", "dodaj", "platnosci"];

export function App() {
  const toast = useToast();
  const route = useHashRoute();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [checking, setChecking] = useState(() => Boolean(session.get()));
  const [eventsCount, setEventsCount] = useState<number | null>(null);

  const logout = useCallback(
    (message?: string) => {
      session.set(null);
      setProfile(null);
      setEventsCount(null);
      history.replaceState(null, "", window.location.pathname);
      if (message) toast(message, "error");
    },
    [toast],
  );

  // 403 = klucz unieważniony (np. usunięty z listy partnerów w Terraformie)
  const handleError = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 403) logout("Sesja wygasła lub klucz został unieważniony.");
      else toast(e instanceof Error ? e.message : "Coś poszło nie tak", "error");
    },
    [logout, toast],
  );

  const refreshProfile = useCallback(async () => {
    try {
      setProfile(await api<Profile>("GET", "/me"));
    } catch (e) {
      handleError(e);
    }
  }, [handleError]);

  const login = useCallback(async (apiKey: string) => {
    const me = await api<Profile>("GET", "/me", undefined, apiKey); // rzuca ApiError(403) przy złym kluczu
    session.set(apiKey);
    setProfile(me);
  }, []);

  useEffect(() => {
    const saved = session.get();
    if (!saved) return;
    login(saved)
      .catch(() => session.set(null))
      .finally(() => setChecking(false));
  }, [login]);

  if (checking) {
    return (
      <div className="loading">
        <span className="spinner" aria-hidden="true" />
        Ładowanie…
      </div>
    );
  }
  if (!profile) return <Login onLogin={login} />;

  const screen: Screen = SCREENS.includes(route.path as Screen) ? (route.path as Screen) : "wydarzenia";
  return (
    <div className="shell">
      <Sidebar profile={profile} active={screen} eventsCount={eventsCount} onLogout={() => logout()} />
      <main className="main">
        {screen === "wydarzenia" && <Events onError={handleError} onCount={setEventsCount} credits={profile.credits} />}
        {screen === "dodaj" && (
          <EventForm
            profile={profile}
            onError={handleError}
            onPublished={async () => {
              await refreshProfile();
              navigate("wydarzenia");
            }}
          />
        )}
        {screen === "platnosci" && <Payments profile={profile} params={route.params} onError={handleError} onRefresh={refreshProfile} />}
      </main>
    </div>
  );
}
