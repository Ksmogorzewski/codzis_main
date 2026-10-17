// Chipy kategorii na ekranie głównym (Wszystko / Sport / Kultura / Rekreacja). API rekomendacji
// nie filtruje po kategorii, więc dzielimy karty na kliencie po tagach taggera (tagger/prompt.py).
// Mapa jak w poprzedniej wersji aplikacji (app/src/server/features/recommendations).

export const CATEGORIES = ["all", "sport", "kultura", "rekreacja"] as const;
export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<Category, string> = {
  all: "Wszystko",
  sport: "Sport",
  kultura: "Kultura",
  rekreacja: "Rekreacja",
};

const SPORT_THEMES = ["Sport", "Rekreacja i fitness"];
const SPORT_FORMATS = ["Trening / zajęcia ruchowe", "Zawody / turniej"];
const CULTURE_THEMES = [
  "Teatr i performans",
  "Muzyka",
  "Film i kino",
  "Sztuki wizualne i wystawy",
  "Literatura",
  "Muzea i dziedzictwo",
  "Historia",
  "Architektura i urbanistyka",
];

type Tags = { theme?: string[]; format?: string[] };

const has = (list: string[] | undefined, wanted: string[]) => (list ?? []).some((v) => wanted.includes(v));

/** Kategoria karty: sport ma pierwszeństwo, potem kultura, reszta to rekreacja. */
export function categoryOf(tags: Tags): Exclude<Category, "all"> {
  if (has(tags.theme, SPORT_THEMES) || has(tags.format, SPORT_FORMATS)) return "sport";
  if (has(tags.theme, CULTURE_THEMES)) return "kultura";
  return "rekreacja";
}

export function filterByCategory<T extends { tags: Tags }>(items: T[], cat: Category): T[] {
  return cat === "all" ? items : items.filter((i) => categoryOf(i.tags) === cat);
}
