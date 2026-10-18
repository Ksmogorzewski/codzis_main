// Tagi z taggera (tagger/prompt.py). Na karcie pokazujemy jeden główny temat, w szczegółach wszystkie.
// Koszt, miejsce i tryb są już widoczne jako cena i plakietki na zdjęciu - nie dublujemy ich na liście tagów.
import type { Card } from "./schemas";

type Tags = Card["tags"];

// Wartości bez informacji (z taksonomii taggera) - pomijamy je w UI.
const UNKNOWN = new Set(["Nieznane", "Brak informacji"]);

/** Główny tag wydarzenia (pierwszy temat) - jedyny tag widoczny na karcie. */
export function mainTag(tags: Tags): string | null {
  const main = tags.theme?.[0];
  return main && !UNKNOWN.has(main) ? main : null;
}

/** Wszystkie tagi do pokazania w szczegółach: temat, format, dla kogo, aktywność, wejście. Bez powtórek. */
export function tagChips(tags: Tags): string[] {
  const chips = [
    ...(tags.theme ?? []),
    ...(tags.format ?? []),
    ...(tags.audience ?? []),
    tags.activity_level,
    tags.registration,
  ].filter((c): c is string => Boolean(c) && !UNKNOWN.has(c as string));
  return [...new Set(chips)];
}
