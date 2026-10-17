// Szczegóły wydarzenia nie mają osobnego endpointu: kartę bierzemy z odpowiedzi rekomendacji
// zapisanych w cache TanStack Query (["recommendations", …]).
import type { Card, Recommendations } from "./schemas";

export type FoundCard = { card: Card; builtAt: string | null };

/** Pierwsza karta o danym id w podanych odpowiedziach, razem z czasem zbudowania indeksu. */
export function findCard(results: readonly (Recommendations | undefined)[], id: string): FoundCard | null {
  for (const r of results) {
    const card = r?.items.find((c) => c.id === id);
    if (r && card) return { card, builtAt: r.index.builtAt };
  }
  return null;
}
