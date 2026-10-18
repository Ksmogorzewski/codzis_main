import { useMyCrews } from "./use-my-crews.query";

/**
 * Suma nieprzeczytanych wiadomości we wszystkich czatach moich ekip (plakietka „Twoje” w nagłówku i dolnym
 * pasku), z GET /api/me/crews. Bez odpowiedzi (ładuje się albo błąd) - 0, bez komunikatu.
 */
export function useCrewUnreadTotal(): number {
  return useMyCrews().data?.unread ?? 0;
}
