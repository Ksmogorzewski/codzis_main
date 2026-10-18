import { useEffect, useRef, useState } from "react";

/** Pas w środku ekranu (10% wysokości): karta, która w nim jest, pokazuje zdjęcie podczas przewijania. */
const CENTER_BAND = "-45% 0px -45% 0px";

/**
 * Odsłanianie zdjęcia na karcie-plakacie. Najechanie myszą i fokus klawiatury obsługuje CSS (group-hover,
 * group-focus-within); ten hook dokłada to, czego CSS nie zrobi: na ekranach dotykowych zdjęcie pokazuje
 * karta na środku ekranu podczas przewijania, a stuknięcie w plakat przełącza zdjęcie.
 * `enabled = false` (brak zdjęcia) - nic nie obserwuje i nic nie przełącza.
 */
export function usePhotoReveal<T extends HTMLElement>(enabled: boolean) {
  const ref = useRef<T>(null);
  const [inCenter, setInCenter] = useState(false);
  const [tapped, setTapped] = useState<boolean | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!enabled || !el || !matchMedia("(hover: none)").matches) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInCenter(entry?.isIntersecting ?? false);
        setTapped(null); // przewinięcie kasuje ręczny wybór: znowu decyduje położenie karty
      },
      { rootMargin: CENTER_BAND },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [enabled]);

  const active = enabled && (tapped ?? inCenter);
  const toggle = () => enabled && setTapped(!active);
  return { ref, active, toggle };
}
