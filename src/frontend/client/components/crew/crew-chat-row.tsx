import { Link } from "@tanstack/react-router";
import { UnreadBadge } from "@/components/layout/nav-badge";
import { Icon } from "@/components/ui/icon";
import { useMyCrews } from "@/hooks/use-my-crews.query";
import { CREW_CAPACITY, messagePreview } from "@/lib/crew-chat";
import { cn } from "@/lib/utils";

/**
 * Wiersz „Czat ekipy” na zakładce „Twoje”: ostatnia wiadomość, liczba nieprzeczytanych i wejście na czat
 * (wszystkie wiersze z jednego GET /api/me/crews). Bez ekipy (czatu jeszcze nie otwierałem) - zachęta do wejścia.
 */
export function CrewChatRow({ id }: { id: string }) {
  const mine = useMyCrews();
  const crew = mine.data?.items.find((c) => c.eventId === id);
  const unread = crew?.unread ?? 0;
  const preview = crew?.last ? messagePreview(crew.last) : mine.data ? `Wejdź i dołącz do ekipy (do ${CREW_CAPACITY} osób)` : null;

  return (
    <Link
      to="/wydarzenie/$id/ekipa"
      params={{ id }}
      className="flex min-h-16 items-center gap-3 border-t px-4 py-3 outline-none transition-colors duration-200 hover:bg-secondary focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-inset"
    >
      <span className="grid size-10 shrink-0 place-items-center bg-foreground text-background">
        <Icon name="forum" size={22} filled />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-base font-bold">Czat ekipy</span>
        {preview && (
          <span className={cn("truncate text-meta text-muted-foreground", unread > 0 && "font-semibold text-foreground")}>
            {preview}
          </span>
        )}
      </span>
      <UnreadBadge count={unread} />
      <Icon name="chevron_right" size={22} className="text-muted-foreground" />
    </Link>
  );
}
