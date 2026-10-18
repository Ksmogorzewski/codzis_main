// Filtry ekranu głównego w adresie (#/?when=…&q=…&cat=…). Zły lub brakujący parametr wraca do
// wartości domyślnej, więc stary albo ręcznie zmieniony link nigdy nie wywraca ekranu.
import { z } from "zod";
import { CATEGORIES } from "./categories";
import { WhenSchema } from "./schemas";
import { readJson, writeJson } from "./storage";

export const MAX_QUERY = 120; // jak MAX_QUERY w src/recommender_api/handler.py

/** "  joga   dla seniorów " -> "joga dla seniorów" (maks. 120 znaków, jak na serwerze). */
export const normalizeQuery = (q: string) => q.split(/\s+/).filter(Boolean).join(" ").slice(0, MAX_QUERY);

// Ekran główny: Dziś / Jutro / Weekend / Inny dzień - bez „7 dni”. Stary link z when=week (i filtr zapamiętany
// w sesji) wraca do dziś; API nadal zna "week".
export const HomeWhenSchema = WhenSchema.exclude(["week"]);
export type HomeWhen = z.infer<typeof HomeWhenSchema>;

export const HomeSearchSchema = z.object({
  when: HomeWhenSchema.default("today").catch("today"),
  // Tylko przy when=date ("Inny dzień"); zakres (do 60 dni naprzód) sprawdza serwer
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional().catch(undefined),
  q: z.string().transform(normalizeQuery).default("").catch(""),
  cat: z.enum(CATEGORIES).default("all").catch("all"),
});

export type HomeSearch = z.output<typeof HomeSearchSchema>;
export const DEFAULT_SEARCH: HomeSearch = { when: "today", q: "", cat: "all" };

export type RecommendationsParams = { when: HomeWhen; q: string; date?: string };

/** Filtry z adresu -> parametry zapytania o rekomendacje. "Inny dzień" bez poprawnej daty = dziś. */
export function recommendationsParams(s: Pick<HomeSearch, "when" | "date" | "q">): RecommendationsParams {
  if (s.when !== "date") return { when: s.when, q: s.q };
  return s.date ? { when: "date", date: s.date, q: s.q } : { when: "today", q: s.q };
}

// Ostatnie filtry: wracamy do nich ze szczegółów i po zapisie profilu. sessionStorage, żeby
// odświeżona strona szczegółów wiedziała, z jakiej listy przyszła karta.
const KEY = "warsawnow-search";

export function rememberSearch(s: HomeSearch): void {
  writeJson("session", KEY, s);
}

export function lastSearch(): HomeSearch {
  const parsed = HomeSearchSchema.safeParse(readJson<unknown>("session", KEY) ?? {});
  return parsed.success ? parsed.data : DEFAULT_SEARCH;
}
