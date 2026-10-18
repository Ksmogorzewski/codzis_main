import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { UnreadBadge } from "@/components/layout/nav-badge";
import { Icon } from "@/components/ui/icon";
import { attendeesQueryOptions } from "@/hooks/use-attendees.query";
import { authorOf, crewMembers, memberNames } from "@/lib/crew-chat";
import { DEMO_CREW, demoInbox } from "@/lib/crew-demo";
import { unreadCount, useInbox } from "@/lib/crew-inbox";
import { cn } from "@/lib/utils";

/**
 * Wiersz „Czat ekipy” na zakładce „Twoje”: ostatnia wiadomość, liczba nieprzeczytanych, wejście na czat.
 * DEMO: wiadomości to scenariusz z lib/crew-demo.ts (ten sam, który pokaże czat), stan przeczytanych
 * z lib/crew-inbox.ts. Imiona ekipy tylko z listy zapisanych, jeśli już jest w pamięci (bez zapytania
 * na każde wydarzenie listy); inaczej imiona z demo.
 */
export function CrewChatRow({ id }: { id: string }) {
  const inbox = useInbox();
  const attendees = useQuery({ ...attendeesQueryOptions(id), enabled: false });
  const members = memberNames(crewMembers(attendees.data?.people, DEMO_CREW.names, DEMO_CREW.capacity - 1));
  const last = demoInbox(members, id, inbox[id]?.arrived ?? 0).at(-1);
  const unread = unreadCount(inbox, id);

  return (
    <Link
      to="/wydarzenie/$id/ekipa"
      params={{ id }}
      className="flex min-h-16 items-center gap-3 border-t px-4 py-3 outline-none transition-colors duration-200 hover:bg-secondary focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-inset"
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary-soft text-primary-ink">
        <Icon name="forum" size={22} filled />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-base font-bold">Czat ekipy</span>
        {last && (
          <span className={cn("truncate text-meta text-muted-foreground", unread > 0 && "font-semibold text-foreground")}>
            {`${authorOf(last)}: ${last.text}`}
          </span>
        )}
      </span>
      <UnreadBadge count={unread} />
      <Icon name="chevron_right" size={22} className="text-muted-foreground" />
    </Link>
  );
}
