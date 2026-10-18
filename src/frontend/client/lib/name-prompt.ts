// Prośba o imię z dowolnego miejsca: trasy znajomych odpowiadają 409 name_required, gdy konto nie ma imienia;
// globalny onError (main.tsx) otwiera wtedy NameDialog w _app.tsx. Imię jest też sprawdzane zaraz po zalogowaniu.
import { useSyncExternalStore } from "react";

export function createNamePrompt() {
  let open = false;
  const listeners = new Set<() => void>();
  const set = (next: boolean) => {
    if (open === next) return;
    open = next;
    for (const l of listeners) l();
  };
  return {
    isOpen: () => open,
    open: () => set(true),
    close: () => set(false),
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export const namePrompt = createNamePrompt();

/** Czy pokazać prośbę o imię (po błędzie name_required). */
export const useNamePrompt = () => useSyncExternalStore(namePrompt.subscribe, namePrompt.isOpen);
