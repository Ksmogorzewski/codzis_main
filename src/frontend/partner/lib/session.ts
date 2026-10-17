// Klucz API partnera = jego "login"; trzymany tylko do zamknięcia karty (sessionStorage)
const KEY = "apiKey";

export const session = {
  get(): string | null {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(apiKey: string | null) {
    try {
      if (apiKey) sessionStorage.setItem(KEY, apiKey);
      else sessionStorage.removeItem(KEY);
    } catch {
      // bez storage logowanie nie przetrwa przeładowania strony
    }
  },
};
