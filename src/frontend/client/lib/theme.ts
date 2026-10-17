import { useSyncExternalStore } from "react";

// Tryb ciemny: klasa .dark na <html> (tokeny w styles.css). Pierwszy stan ustawia skrypt w index.html
// (zapisany wybór albo ustawienie systemu, bez mignięcia jasnego tła); zapis tylko po kliknięciu.
const KEY = "warsawnow-theme";
const listeners = new Set<() => void>();

const isDark = () => typeof document !== "undefined" && document.documentElement.classList.contains("dark");

export function toggleDark(): void {
  const next = !isDark();
  document.documentElement.classList.toggle("dark", next);
  try {
    localStorage.setItem(KEY, next ? "dark" : "light");
  } catch {
    // bez zapisu motyw wróci do domyślnego po przeładowaniu
  }
  for (const l of listeners) l();
}

export function useDark(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    isDark,
    () => false,
  );
}
