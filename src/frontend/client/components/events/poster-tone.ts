import type { Category } from "@/lib/categories";

type Tone = Exclude<Category, "all">;

/** Pole plakatu karty / szczegółów: płaski kolor kategorii i kolor tekstu na nim. */
export const POSTER_FIELD: Record<Tone, string> = {
  kultura: "bg-poster-kultura text-poster-kultura-foreground",
  sport: "bg-poster-sport text-poster-sport-foreground",
  rekreacja: "bg-poster-rekreacja text-poster-rekreacja-foreground",
};

/** Ciemniejszy odcień tego samego koloru: wielka godzina w tle plakatu. */
export const POSTER_SHADE: Record<Tone, string> = {
  kultura: "text-poster-kultura-shade",
  sport: "text-poster-sport-shade",
  rekreacja: "text-poster-rekreacja-shade",
};

/** Kwadrat koloru przy nazwie kategorii w filtrach. */
export const POSTER_SWATCH: Record<Tone, string> = {
  kultura: "bg-poster-kultura",
  sport: "bg-poster-sport",
  rekreacja: "bg-poster-rekreacja",
};
