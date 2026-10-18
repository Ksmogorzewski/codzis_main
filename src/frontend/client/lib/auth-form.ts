// Kroki formularza logowania i walidacja pól przed wysłaniem do Cognito (czysta logika, testy obok).
import { z } from "zod";

export type AuthMode = "login" | "register" | "confirm" | "reset" | "resetConfirm";

export type AuthFormValues = {
  name: string;
  /** Nazwisko (opcjonalnie): innym pokazujemy tylko inicjał („Ola K.”). */
  familyName: string;
  email: string;
  password: string;
  code: string;
  newPassword: string;
};

export const AUTH_TITLES: Record<AuthMode, string> = {
  login: "Zaloguj się",
  register: "Załóż konto",
  confirm: "Potwierdź e-mail",
  reset: "Nie pamiętasz hasła?",
  resetConfirm: "Ustaw nowe hasło",
};

export const AUTH_SUBMIT: Record<AuthMode, string> = {
  login: "Zaloguj się",
  register: "Utwórz konto",
  confirm: "Potwierdź",
  reset: "Wyślij kod",
  resetConfirm: "Zapisz hasło i zaloguj",
};

export const PASSWORD_HINT = "Min. 8 znaków, w tym mała litera i cyfra.";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const CODE_RE = /^\d{6}$/;

export const MAX_NAME = 40;
const NAME_RE = /^\p{L}+(?:[ -]+\p{L}+)*$/u;

/** Spacje skrócone do pojedynczych, znaki złożone w jeden (NFC: „Z” + kropka = „Ż”). */
const collapseName = (raw: string) => raw.normalize("NFC").split(/\s+/).filter(Boolean).join(" ");

/** Imię do Cognito: przycięte, pojedyncze spacje, maks. 40 znaków ("" = brak). */
export const normalizeName = (raw: string) => collapseName(raw).slice(0, MAX_NAME);

/** Imię z rejestracji i z jednorazowej prośby: litery (także polskie), spacje i myślnik. */
export const NameSchema = z
  .string()
  .transform(collapseName)
  .pipe(
    z
      .string()
      .min(1, "Podaj imię.")
      .max(MAX_NAME, `Imię może mieć najwyżej ${MAX_NAME} znaków.`)
      .regex(NAME_RE, "Imię może zawierać tylko litery, spacje i myślnik."),
  );

/** Komunikat błędu imienia albo null, gdy poprawne. */
export function nameError(raw: string): string | null {
  const r = NameSchema.safeParse(raw);
  return r.success ? null : (r.error.issues[0]?.message ?? "Podaj imię.");
}

/** Nazwisko z rejestracji (opcjonalne): puste = brak, inaczej te same reguły co imię. */
export const FamilyNameSchema = z
  .string()
  .transform(collapseName)
  .pipe(
    z
      .string()
      .max(MAX_NAME, `Nazwisko może mieć najwyżej ${MAX_NAME} znaków.`)
      .refine((v) => v === "" || NAME_RE.test(v), "Nazwisko może zawierać tylko litery, spacje i myślnik."),
  );

/** Komunikat błędu nazwiska albo null (także gdy puste). */
export function familyNameError(raw: string): string | null {
  const r = FamilyNameSchema.safeParse(raw);
  return r.success ? null : (r.error.issues[0]?.message ?? "Popraw nazwisko.");
}

/** Pola widoczne w danym kroku. Imię i nazwisko tylko przy rejestracji (później ich nie zmieniamy). */
export const showsName = (mode: AuthMode) => mode === "register";
export const showsEmail = (mode: AuthMode) => mode === "login" || mode === "register" || mode === "reset";
export const showsPassword = (mode: AuthMode) => mode === "login" || mode === "register";
export const showsCode = (mode: AuthMode) => mode === "confirm" || mode === "resetConfirm";

/** Kod z e-maila: same cyfry, najwyżej 6 (wklejony tekst ze spacjami też przejdzie). */
export const normalizeCode = (raw: string) => raw.replace(/\D/g, "").slice(0, 6);

/** Komunikat błędu albo null, gdy można wysłać. */
export function validateAuthForm(mode: AuthMode, v: AuthFormValues): string | null {
  const badName = showsName(mode) ? nameError(v.name) : null;
  if (badName) return badName;
  const badFamilyName = showsName(mode) ? familyNameError(v.familyName) : null;
  if (badFamilyName) return badFamilyName;
  if (showsEmail(mode) && !EMAIL_RE.test(v.email.trim())) return "Podaj poprawny adres e-mail.";
  if (mode === "login" && !v.password) return "Podaj hasło.";
  if (mode === "register" && v.password.length < 8) return "Hasło musi mieć min. 8 znaków, w tym małą literę i cyfrę.";
  if (showsCode(mode) && !CODE_RE.test(v.code)) return "Wpisz 6-cyfrowy kod z e-maila.";
  if (mode === "resetConfirm" && v.newPassword.length < 8) return "Nowe hasło musi mieć min. 8 znaków.";
  return null;
}
