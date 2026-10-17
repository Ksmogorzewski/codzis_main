import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../shared/Icon";
import { readJson, writeJson } from "../shared/storage";
import { useToast } from "../shared/toast";
import { navigate, useHashRoute } from "../shared/useHashRoute";
import { Header } from "./components/Header";
import { Home } from "./components/Home";
import { Landing } from "./components/Landing";
import { Survey } from "./components/Survey";
import { ApiError, api } from "./lib/api";
import { AuthError, getIdToken, handleRedirect, signOut } from "./lib/auth";
import type { Answers, Me, Onboarding } from "./lib/types";
import { sanitize } from "./lib/wizard";

type Phase =
  | { kind: "loading"; text?: string }
  | { kind: "auth"; error?: string }
  | { kind: "error"; message: string }
  | { kind: "app" };

// Niezapisane odpowiedzi przetrwają przeładowanie strony
const draftKey = (userId: string) => `warsawnow-draft-${userId}`;

export function App() {
  const toast = useToast();
  const route = useHashRoute();
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [me, setMe] = useState<Me | null>(null);
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [answers, setAnswersState] = useState<Answers>({});
  const started = useRef(false);

  const enterApp = useCallback(async () => {
    setPhase({ kind: "loading" });
    try {
      const [profile, questions] = await Promise.all([api<Me>("GET", "/api/me"), api<Onboarding>("GET", "/api/onboarding")]);
      const draft = readJson<Answers>("local", draftKey(profile.userId));
      setMe(profile);
      setOnboarding(questions);
      setAnswersState(sanitize(questions.steps, draft ?? profile.profile?.answers));
      setPhase({ kind: "app" });
      if (profile.needsOnboarding) navigate("profil");
      else if (profile.onboardingOutdated) {
        navigate("profil");
        toast("Dodaliśmy nowe pytania – uzupełnij profil.");
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setPhase({ kind: "auth", error: e.message });
      else setPhase({ kind: "error", message: e instanceof Error ? e.message : "Nie udało się wczytać profilu." });
    }
  }, [toast]);

  // Start: powrót z logowania Google albo istniejąca sesja
  useEffect(() => {
    if (started.current) return; // StrictMode uruchamia efekt dwa razy, a kod z Google jest jednorazowy
    started.current = true;
    (async () => {
      try {
        if (await handleRedirect()) toast("Zalogowano przez Google");
      } catch (e) {
        setPhase({ kind: "auth", error: e instanceof AuthError ? e.message : "Logowanie nie powiodło się." });
        return;
      }
      const token = await getIdToken().catch(() => null);
      if (token) await enterApp();
      else setPhase({ kind: "auth" });
    })();
  }, [enterApp, toast]);

  const setAnswers = useCallback(
    (next: Answers) => {
      setAnswersState(next);
      if (me) writeJson("local", draftKey(me.userId), next);
    },
    [me],
  );

  const saveProfile = useCallback(async () => {
    const saved = await api<Me>("PUT", "/api/profile", { answers });
    writeJson("local", draftKey(saved.userId), null);
    setMe(saved);
    if (onboarding) setAnswersState(sanitize(onboarding.steps, saved.profile?.answers));
    toast("Profil zapisany");
    navigate("rekomendacje");
  }, [answers, onboarding, toast]);

  const logout = useCallback(async () => {
    setPhase({ kind: "loading", text: "Wylogowywanie…" });
    if (await signOut()) return; // przekierowanie do wylogowania z Google
    setMe(null);
    setOnboarding(null);
    setAnswersState({});
    history.replaceState(null, "", "/");
    setPhase({ kind: "auth" });
  }, []);

  if (phase.kind === "loading") {
    return (
      <div className="loading">
        <span className="spinner" aria-hidden="true" />
        <span>{phase.text ?? "Ładowanie…"}</span>
      </div>
    );
  }
  if (phase.kind === "auth") return <Landing initialError={phase.error} onSignedIn={enterApp} />;
  if (phase.kind === "error" || !me || !onboarding) {
    return (
      <div className="loading">
        <Icon name="cloud_off" size={40} />
        <span>{phase.kind === "error" ? phase.message : "Nie udało się wczytać profilu."}</span>
        <div className="row-gap">
          <button className="btn" type="button" onClick={enterApp}>Spróbuj ponownie</button>
          <button className="btn btn-outline" type="button" onClick={logout}>Wyloguj</button>
        </div>
      </div>
    );
  }

  const screen = me.needsOnboarding || route.path === "profil" ? "survey" : "home";
  return (
    <>
      <Header active={screen} onLogout={logout} />
      {screen === "survey" ? (
        <Survey steps={onboarding.steps} answers={answers} onChange={setAnswers} onSave={saveProfile} firstTime={me.needsOnboarding} />
      ) : (
        <Home me={me} steps={onboarding.steps} />
      )}
    </>
  );
}
