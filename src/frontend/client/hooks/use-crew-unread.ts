import { totalUnread, useInbox } from "@/lib/crew-inbox";
import { useMyEvents } from "./use-my-events.query";

/**
 * Suma nieprzeczytanych wiadomości we wszystkich czatach moich wydarzeń (plakietka „Twoje” w nagłówku
 * i dolnym pasku). DEMO: wiadomości to scenariusz z lib/crew-demo.ts, stan przeczytanych lokalnie.
 * Bez listy zapisów (ładuje się albo błąd) - 0, bez komunikatu.
 */
export function useCrewUnreadTotal(): number {
  const mine = useMyEvents();
  const inbox = useInbox();
  return totalUnread(inbox, mine.data?.items.map((c) => c.id) ?? []);
}
