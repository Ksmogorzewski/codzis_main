import { useCallback, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "warsawnow-theme";

// Motyw ustawia skrypt w index.html (zapisany wybór albo ustawienie systemu); zapis tylko po kliknięciu
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // bez zapisu motyw wróci do domyślnego po przeładowaniu
      }
      return next;
    });
  }, []);
  return [theme, toggle];
}
