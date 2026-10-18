import { useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { type FormEvent, type ReactNode, useState } from "react";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { meQueryOptions } from "@/hooks/use-me.query";
import {
  type AuthFailure,
  type AuthResult,
  confirmForgotPassword,
  confirmSignUp,
  forgotPassword,
  googleAvailable,
  resendCode,
  signIn,
  signInWithGoogle,
  signUp,
} from "@/lib/auth";
import {
  AUTH_SUBMIT,
  AUTH_TITLES,
  type AuthMode,
  MAX_NAME,
  normalizeCode,
  PASSWORD_HINT,
  showsCode,
  showsEmail,
  showsName,
  showsPassword,
  validateAuthForm,
} from "@/lib/auth-form";
import { config } from "@/lib/config";
import { afterLoginTarget, rememberGoogleTarget, rememberTarget } from "@/lib/login-redirect";
import { onboardingRedirect } from "@/lib/onboarding-hint";
import { ok } from "@/lib/result";

const loginRoute = getRouteApi("/login");

const safeHref = (url: string) => (/^https?:\/\//.test(url) ? url : null);

/**
 * Formularz logowania: logowanie, rejestracja z kodem z e-maila, reset hasła (Cognito przez fetch)
 * i „Kontynuuj z Google” (Hosted UI). initialError = komunikat nieudanego powrotu z Google.
 */
export function AuthForm({ initialError = null }: { initialError?: string | null }) {
  const navigate = useNavigate();
  const search = loginRoute.useSearch();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AuthMode>("login");
  const [name, setName] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Błąd logowania Google: w tym samym alercie, ale bez oznaczania pól formularza jako błędnych
  const [googleError, setGoogleError] = useState<string | null>(initialError);
  const [info, setInfo] = useState<string | null>(null);

  const mail = email.trim();

  function go(next: AuthMode, message: string | null = null) {
    setMode(next);
    setError(null);
    setGoogleError(null);
    setInfo(message);
    setCode("");
  }

  // Po zalogowaniu: profil z API decyduje, czy najpierw ankieta, czy od razu propozycje
  // (albo ekran, na który ktoś wszedł bez sesji, np. zaproszenie do znajomych z QR).
  async function afterSignIn() {
    queryClient.clear(); // bez danych poprzedniego użytkownika
    try {
      const me = await queryClient.fetchQuery(meQueryOptions);
      // przy ankiecie adres zaproszenia czeka na jej zapis (survey-view.tsx); bez ankiety - stary czyścimy
      // nowe pytania w wypełnionym profilu nie zatrzymują - prosi o nie baner na ekranie głównym
      const to = onboardingRedirect(me);
      rememberTarget(to ? afterLoginTarget(search) : null);
      if (to) await navigate({ to });
      else await navigate({ href: afterLoginTarget(search) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się wczytać profilu.");
    }
  }

  // Błędy Cognito, które zmieniają krok formularza zamiast tylko pokazać komunikat.
  async function handleFailure(failure: AuthFailure) {
    if (failure.code === "UserNotConfirmedException") {
      await resendCode(mail);
      go("confirm", `Konto nie jest jeszcze potwierdzone. Wysłaliśmy kod na ${mail}.`);
    } else if (failure.code === "UsernameExistsException") {
      go("login");
      setError(failure.message);
    } else {
      setError(failure.message);
    }
  }

  async function signInAndContinue(pass: string): Promise<AuthResult<void>> {
    const r = await signIn(mail, pass);
    if (r.error === null) await afterSignIn();
    return r;
  }

  async function submitStep(): Promise<AuthResult<void>> {
    switch (mode) {
      case "login":
        return signInAndContinue(password);
      case "register": {
        const r = await signUp(mail, password, name, familyName);
        if (r.error !== null) return r;
        go("confirm", `Wysłaliśmy 6-cyfrowy kod na ${r.data}.`);
        return ok(undefined);
      }
      case "confirm": {
        const r = await confirmSignUp(mail, code);
        if (r.error !== null) return r;
        if (password) return signInAndContinue(password);
        go("login", "Konto potwierdzone – zaloguj się.");
        return r;
      }
      case "reset": {
        const r = await forgotPassword(mail);
        if (r.error === null) go("resetConfirm", `Jeśli konto istnieje, wysłaliśmy kod na ${mail}.`);
        return r;
      }
      case "resetConfirm": {
        const r = await confirmForgotPassword(mail, code, newPassword);
        return r.error === null ? signInAndContinue(newPassword) : r;
      }
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validateAuthForm(mode, { name, familyName, email, password, code, newPassword });
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    setGoogleError(null);
    const r = await submitStep();
    if (r.error !== null) await handleFailure(r.error);
    setBusy(false);
  }

  // Przekierowanie do Google; po powrocie sesję zapisuje strażnik tras (lib/auth.ts: googleSignInResult),
  // a ekran z ?redirect=… (np. zaproszenie z QR) czeka w sessionStorage (lib/login-redirect.ts).
  async function onGoogle() {
    setBusy(true);
    setError(null);
    setGoogleError(null);
    rememberGoogleTarget(search);
    try {
      await signInWithGoogle();
    } catch {
      setGoogleError("Nie udało się rozpocząć logowania przez Google. Spróbuj ponownie.");
      setBusy(false);
    }
  }

  async function onResend() {
    setBusy(true);
    setError(null);
    const r = await resendCode(mail);
    if (r.error !== null) setError(r.error.message);
    else setInfo(`Wysłaliśmy nowy kod na ${mail}.`);
    setBusy(false);
  }

  const partnerHref = safeHref(config().partnerPortal);

  return (
    <form className="flex w-full max-w-[400px] flex-col gap-4" onSubmit={onSubmit} noValidate>
      <h2 className="mb-1 text-[28px] font-extrabold tracking-[-0.02em]">{AUTH_TITLES[mode]}</h2>
      {info && (
        <p role="status" className="text-base text-muted-foreground">
          {info}
        </p>
      )}

      {showsName(mode) && (
        <Field id="auth-name" label="Imię">
          <Input
            id="auth-name"
            autoComplete="given-name"
            placeholder="np. Anna"
            maxLength={MAX_NAME}
            value={name}
            aria-invalid={error ? true : undefined}
            aria-describedby="auth-name-hint"
            onChange={(e) => setName(e.target.value)}
          />
          <p id="auth-name-hint" className="text-meta text-muted-foreground">
            Zobaczą je inni zapisani na to samo wydarzenie. Później go nie zmienisz.
          </p>
        </Field>
      )}
      {showsName(mode) && (
        <Field id="auth-family-name" label="Nazwisko (opcjonalnie)">
          <Input
            id="auth-family-name"
            autoComplete="family-name"
            placeholder="np. Kowalska"
            maxLength={MAX_NAME}
            value={familyName}
            aria-invalid={error ? true : undefined}
            aria-describedby="auth-family-name-hint"
            onChange={(e) => setFamilyName(e.target.value)}
          />
          <p id="auth-family-name-hint" className="text-meta text-muted-foreground">
            Inni zobaczą tylko pierwszą literę, np. „Anna K.”. Później go nie zmienisz.
          </p>
        </Field>
      )}
      {showsEmail(mode) && (
        <Field id="auth-email" label="E-mail">
          <Input
            id="auth-email"
            type="email"
            autoComplete="email"
            placeholder="np. anna@example.pl"
            value={email}
            aria-invalid={error ? true : undefined}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
      )}
      {showsPassword(mode) && (
        <Field id="auth-password" label="Hasło">
          <Input
            id="auth-password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            aria-invalid={error ? true : undefined}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
      )}
      {showsCode(mode) && (
        <Field id="auth-code" label="Kod z e-maila">
          <Input
            id="auth-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="6 cyfr"
            className="font-semibold tracking-[0.3em]"
            value={code}
            aria-invalid={error ? true : undefined}
            onChange={(e) => setCode(normalizeCode(e.target.value))}
          />
        </Field>
      )}
      {mode === "resetConfirm" && (
        <Field id="auth-new-password" label="Nowe hasło">
          <Input
            id="auth-new-password"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            aria-invalid={error ? true : undefined}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </Field>
      )}
      {(mode === "register" || mode === "resetConfirm") && (
        <p className="-mt-2 text-meta text-muted-foreground">{PASSWORD_HINT}</p>
      )}

      {(error ?? googleError) && (
        <Alert variant="destructive">
          <Icon name="error" size={22} className="mt-px" />
          <AlertTitle className="font-semibold">{error ?? googleError}</AlertTitle>
        </Alert>
      )}

      <Button type="submit" variant="brand" size="lg" className="mt-1 h-[58px] text-lg" disabled={busy}>
        {busy ? "Chwileczkę…" : AUTH_SUBMIT[mode]}
      </Button>

      <div className="flex flex-wrap justify-center gap-x-6 gap-y-2">
        {mode === "login" && <LinkButton onClick={() => go("reset")}>Nie pamiętasz hasła?</LinkButton>}
        {mode === "confirm" && (
          <LinkButton onClick={onResend} disabled={busy}>
            Wyślij kod ponownie
          </LinkButton>
        )}
        {(mode === "confirm" || mode === "reset" || mode === "resetConfirm") && (
          <LinkButton onClick={() => go("login")}>Wróć do logowania</LinkButton>
        )}
      </div>

      {(mode === "login" || mode === "register") && googleAvailable() && (
        <>
          <div className="flex items-center gap-3 text-meta text-muted-foreground">
            <Separator className="w-auto flex-1" />
            lub
            <Separator className="w-auto flex-1" />
          </div>
          <Button type="button" variant="outline" size="lg" className="h-[58px] text-lg" disabled={busy} onClick={onGoogle}>
            <img src="/assets/google.svg" alt="" width={22} height={22} className="size-[22px]" />
            Kontynuuj z Google
          </Button>
        </>
      )}

      {(mode === "login" || mode === "register") && (
        <p className="mt-1 text-center text-base text-muted-foreground">
          {mode === "login" ? "Nie masz konta?" : "Masz już konto?"}{" "}
          <LinkButton onClick={() => go(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Załóż konto" : "Zaloguj się"}
          </LinkButton>
        </p>
      )}

      {partnerHref && (
        <p className="border-t pt-4 text-center text-meta text-muted-foreground">
          Organizujesz wydarzenia?{" "}
          <a className="font-bold text-brand-ink underline-offset-4 hover:underline" href={partnerHref}>
            Panel organizatora
          </a>
        </p>
      )}
      <p className="text-center text-meta text-muted-foreground">
        <a
          className="rounded-sm underline underline-offset-4 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring"
          href="/polityka-prywatnosci.html"
        >
          Polityka prywatności
        </a>
      </p>
    </form>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function LinkButton(props: { onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <Button type="button" variant="link" size="inline" className="text-base font-bold" {...props} />
  );
}
