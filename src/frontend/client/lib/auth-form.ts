// Kroki formularza logowania i walidacja pól przed wysłaniem do Cognito (czysta logika, testy obok).

export type AuthMode = "login" | "register" | "confirm" | "reset" | "resetConfirm";

export type AuthFormValues = { email: string; password: string; code: string; newPassword: string };

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

/** Pola widoczne w danym kroku. */
export const showsEmail = (mode: AuthMode) => mode === "login" || mode === "register" || mode === "reset";
export const showsPassword = (mode: AuthMode) => mode === "login" || mode === "register";
export const showsCode = (mode: AuthMode) => mode === "confirm" || mode === "resetConfirm";

/** Kod z e-maila: same cyfry, najwyżej 6 (wklejony tekst ze spacjami też przejdzie). */
export const normalizeCode = (raw: string) => raw.replace(/\D/g, "").slice(0, 6);

/** Komunikat błędu albo null, gdy można wysłać. */
export function validateAuthForm(mode: AuthMode, v: AuthFormValues): string | null {
  if (showsEmail(mode) && !EMAIL_RE.test(v.email.trim())) return "Podaj poprawny adres e-mail.";
  if (mode === "login" && !v.password) return "Podaj hasło.";
  if (mode === "register" && v.password.length < 8) return "Hasło musi mieć min. 8 znaków, w tym małą literę i cyfrę.";
  if (showsCode(mode) && !CODE_RE.test(v.code)) return "Wpisz 6-cyfrowy kod z e-maila.";
  if (mode === "resetConfirm" && v.newPassword.length < 8) return "Nowe hasło musi mieć min. 8 znaków.";
  return null;
}
