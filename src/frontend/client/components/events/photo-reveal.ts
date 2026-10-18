// Odsłanianie zdjęcia na polu plakatu (karta i nagłówek szczegółów): zdjęcie wysuwa się od dołu (250 ms, wyhamowanie).
// Trzy wyzwalacze na elemencie z klasą `group/poster`: najechanie myszą i fokus klawiatury (CSS) oraz data-active
// (hooks/use-photo-reveal.ts: plakat na środku ekranu dotykowego albo stuknięcie w plakat).
export const PHOTO_REVEAL =
  "absolute inset-0 [clip-path:inset(100%_0_0_0)] motion-safe:transition-[clip-path] motion-safe:duration-[250ms] motion-safe:ease-[cubic-bezier(.16,1,.3,1)] group-hover/poster:[clip-path:inset(0)] group-focus-within/poster:[clip-path:inset(0)] group-data-[active=true]/poster:[clip-path:inset(0)]";

/** Godzina w tle i znaczek aparatu znikają, gdy zdjęcie jest odsłonięte. */
export const HIDDEN_WHEN_SHOWN =
  "group-hover/poster:opacity-0 group-focus-within/poster:opacity-0 group-data-[active=true]/poster:opacity-0";
