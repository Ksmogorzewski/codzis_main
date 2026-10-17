import { useState, type FormEvent } from "react";
import {
  AuthError,
  confirmForgotPassword,
  confirmSignUp,
  forgotPassword,
  resendCode,
  signIn,
  signInWithGoogle,
  signUp,
} from "../lib/auth";
import { config } from "../lib/config";

type Mode = "login" | "register" | "confirm" | "reset" | "resetConfirm";

const TITLES: Record<Mode, string> = {
  login: "Zaloguj się",
  register: "Załóż konto",
  confirm: "Potwierdź e-mail",
  reset: "Nie pamiętasz hasła?",
  resetConfirm: "Ustaw nowe hasło",
};
const SUBMIT: Record<Mode, string> = {
  login: "Zaloguj się",
  register: "Utwórz konto",
  confirm: "Potwierdź",
  reset: "Wyślij kod",
  resetConfirm: "Zapisz hasło i zaloguj",
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Props = { initialError?: string; onSignedIn: () => void };

export function AuthCard({ initialError, onSignedIn }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError ?? "");
  const [info, setInfo] = useState("");

  const go = (next: Mode, message = "") => {
    setMode(next);
    setError("");
    setInfo(message);
    setCode("");
  };

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      if (e instanceof AuthError && e.code === "UserNotConfirmedException") {
        await resendCode(email).catch(() => {});
        go("confirm", `Konto nie jest jeszcze potwierdzone. Wysłaliśmy kod na ${email}.`);
      } else if (e instanceof AuthError && e.code === "UsernameExistsException") {
        go("login");
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "Coś poszło nie tak. Spróbuj ponownie.");
      }
    } finally {
      setBusy(false);
    }
  }

  function validate(): string | null {
    const needsEmail = mode === "login" || mode === "register" || mode === "reset";
    if (needsEmail && !EMAIL_RE.test(email.trim())) return "Podaj poprawny adres e-mail.";
    if (mode === "login" && !password) return "Podaj hasło.";
    if (mode === "register" && password.length < 8) return "Hasło musi mieć min. 8 znaków, w tym małą literę i cyfrę.";
    if ((mode === "confirm" || mode === "resetConfirm") && !/^\d{4,8}$/.test(code.trim())) return "Wpisz kod z e-maila.";
    if (mode === "resetConfirm" && newPassword.length < 8) return "Nowe hasło musi mieć min. 8 znaków.";
    return null;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    const mail = email.trim();
    void run(async () => {
      switch (mode) {
        case "login":
          await signIn(mail, password);
          onSignedIn();
          break;
        case "register": {
          const r = await signUp(mail, password);
          go("confirm", `Wysłaliśmy 6-cyfrowy kod na ${r.CodeDeliveryDetails?.Destination ?? mail}.`);
          break;
        }
        case "confirm":
          await confirmSignUp(mail, code.trim());
          if (password) {
            await signIn(mail, password);
            onSignedIn();
          } else go("login", "Konto potwierdzone – zaloguj się.");
          break;
        case "reset":
          await forgotPassword(mail);
          go("resetConfirm", `Jeśli konto istnieje, wysłaliśmy kod na ${mail}.`);
          break;
        case "resetConfirm":
          await confirmForgotPassword(mail, code.trim(), newPassword);
          await signIn(mail, newPassword);
          onSignedIn();
          break;
      }
    });
  }

  const link = (label: string, onClick: () => void) => (
    <a
      href="#"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
    >
      {label}
    </a>
  );

  const showGoogle = config().googleEnabled && (mode === "login" || mode === "register");

  return (
    <form className="auth-card" onSubmit={onSubmit} noValidate>
      <h2>{TITLES[mode]}</h2>
      {info && <p className="auth-sub">{info}</p>}

      {(mode === "login" || mode === "register" || mode === "reset") && (
        <label className="field">
          E-mail
          <input type="email" autoComplete="email" placeholder="np. anna@example.pl" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      )}
      {(mode === "login" || mode === "register") && (
        <label className="field">
          Hasło
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
      )}
      {(mode === "confirm" || mode === "resetConfirm") && (
        <label className="field">
          Kod z e-maila
          <input inputMode="numeric" autoComplete="one-time-code" maxLength={8} placeholder="6 cyfr" value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
      )}
      {mode === "resetConfirm" && (
        <label className="field">
          Nowe hasło
          <input type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </label>
      )}
      {(mode === "register" || mode === "resetConfirm") && <p className="field-hint">Min. 8 znaków, w tym mała litera i cyfra.</p>}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <button className="btn btn-red btn-xl" type="submit" disabled={busy}>
        {busy ? "Chwileczkę…" : SUBMIT[mode]}
      </button>

      <div className="auth-links">
        {mode === "login" && link("Nie pamiętasz hasła?", () => go("reset"))}
        {mode === "confirm" &&
          link("Wyślij kod ponownie", () => void run(async () => {
            await resendCode(email.trim());
            setInfo(`Wysłaliśmy nowy kod na ${email.trim()}.`);
          }))}
        {(mode === "confirm" || mode === "reset" || mode === "resetConfirm") && link("Wróć do logowania", () => go("login"))}
      </div>

      {showGoogle && (
        <div>
          <div className="divider">
            <span>lub</span>
          </div>
          <button className="btn btn-outline btn-xl google-btn" type="button" disabled={busy} onClick={() => void run(signInWithGoogle)}>
            <span className="google-g" aria-hidden="true">G</span>Kontynuuj przez Google
          </button>
        </div>
      )}

      {mode === "login" && <p className="auth-switch">Nie masz konta? {link("Załóż konto", () => go("register"))}</p>}
      {mode === "register" && <p className="auth-switch">Masz już konto? {link("Zaloguj się", () => go("login"))}</p>}
      <p className="auth-org">
        Organizujesz wydarzenia? <a href={config().partnerPortal}>Panel organizatora</a>
      </p>
    </form>
  );
}
