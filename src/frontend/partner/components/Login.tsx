import { useState, type FormEvent } from "react";
import { creditsLabel, formatMoney } from "../../shared/format";
import { googleLogin, signIn } from "../lib/auth";
import { config, sortedPackages } from "../lib/config";

type Props = { onLogin: (apiKey: string) => Promise<void> };

// Z Google w config.js (infra/partner_auth.tf): przycisk Google; bez niego: klucz API partnera.
export function Login({ onLogin }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const google = googleLogin();

  async function signInWithGoogle() {
    setBusy(true);
    setError("");
    try {
      await signIn(); // przekierowanie do Google, powrót obsługuje App
    } catch {
      setError("Nie udało się rozpocząć logowania przez Google. Spróbuj ponownie.");
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError("Wpisz klucz API.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onLogin(apiKey.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nie udało się zalogować");
    } finally {
      setBusy(false);
    }
  }

  const packages = sortedPackages();
  const cheapest = Math.min(...packages.map((p) => p.price / p.credits));
  const cfg = config();

  return (
    <div className="login">
      <div className="login-form">
        <div className="login-brand">
          <img src="/assets/logo.jpg" alt="" />
          <b>WarsawNow</b>
          <span className="badge-org">Organizator</span>
        </div>
        <form className="login-box" onSubmit={submit} noValidate>
          <div>
            <h1>Zaloguj się do panelu</h1>
            <p>Dodawaj wydarzenia i docieraj do osób, którym naprawdę pasują.</p>
          </div>
          {!google && (
            <label className="field">
              Klucz API
              <input type="password" autoComplete="current-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              <span className="field-hint">Klucz dostajesz przy rejestracji organizatora. Traktuj go jak hasło.</span>
            </label>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {google ? (
            <button className="btn btn-ghost btn-google" type="button" disabled={busy} onClick={signInWithGoogle}>
              <img src="/assets/google.svg" alt="" width={18} height={18} />
              {busy ? "Przekierowanie…" : "Zaloguj się przez Google"}
            </button>
          ) : (
            <button className="btn btn-dark" type="submit" disabled={busy}>
              {busy ? "Logowanie…" : "Zaloguj się"}
            </button>
          )}
          <span className="muted">
            {google
              ? "Nowy organizator? Zaloguj się kontem Google – konto organizatora założy się samo, a ogłoszenia podpiszemy imieniem i nazwiskiem z tego konta."
              : "Nowy organizator? Napisz do nas – przygotujemy klucz dla Twojej instytucji."}
          </span>
        </form>
        {cfg.clientPortal && (
          <span className="muted">
            Szukasz, co robić w mieście? <a href={cfg.clientPortal}>Przejdź do aplikacji WarsawNow</a> ·{" "}
            <a href={`${cfg.clientPortal}/polityka-prywatnosci.html`}>Polityka prywatności</a>
          </span>
        )}
      </div>

      <div className="login-side">
        <div className="eyebrow">Jak to działa</div>
        <div className="stat-grid">
          <div>
            <span>Jedno ogłoszenie</span>
            <span>{creditsLabel(cfg.eventCost)}</span>
          </div>
          <div>
            <span>Kredyt już od</span>
            <span>{formatMoney(cheapest, cfg.currency)}</span>
          </div>
          <div>
            <span>Publikacja i tagowanie AI</span>
            <span>~2 min</span>
          </div>
          <div>
            <span>Parametry dopasowania</span>
            <span>10</span>
          </div>
        </div>
        <p>
          Każde ogłoszenie jest automatycznie opisywane tagami (temat, dla kogo, format, koszt, dostępność) i trafia do rekomendacji
          dla mieszkańców, którym pasuje.
        </p>
      </div>
    </div>
  );
}
