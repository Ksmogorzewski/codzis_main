// Pozycja z przeglądarki – do liczenia odległości (lib/geo.ts) i jako start trasy w osadzonej mapie Google
// w szczegółach (lib/maps.ts). Do naszego API jej nie wysyłamy.
import { useSyncExternalStore } from "react";
import type { Point } from "./geo";

export type LocationStatus = "pending" | "granted" | "denied" | "unavailable";
export type LocationState = { position: Point | null; status: LocationStatus };

let state: LocationState = { position: null, status: "pending" };
let started = false;
const listeners = new Set<() => void>();

function set(next: LocationState) {
  state = next;
  for (const l of listeners) l();
}

/** Pyta o pozycję raz na sesję strony (timeout 8 s); po odmowie nie pyta ponownie. */
export function startLocation(): void {
  if (started) return;
  started = true;
  if (!("geolocation" in navigator)) {
    set({ position: null, status: "unavailable" });
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (p) => set({ position: { lat: p.coords.latitude, lon: p.coords.longitude }, status: "granted" }),
    (e) => set({ position: null, status: e.code === e.PERMISSION_DENIED ? "denied" : "unavailable" }),
    { timeout: 8000, maximumAge: 5 * 60_000 },
  );
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
};
const snapshot = () => state;

export const useLocation = (): LocationState => useSyncExternalStore(subscribe, snapshot, snapshot);
