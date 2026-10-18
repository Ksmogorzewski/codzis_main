import { getRouteApi, Link } from "@tanstack/react-router";
import { type ReactNode, useEffect } from "react";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendees } from "@/hooks/use-attendees.query";
import { useEvent } from "@/hooks/use-event.query";
import { useEventCard } from "@/hooks/use-event-card.query";
import { currentName } from "@/lib/auth";
import { CATEGORY_LABEL, categoryOf } from "@/lib/categories";
import { crewMembers, memberNames, membersLine, ownLabel } from "@/lib/crew-chat";
import { DEMO_CREW, demoInbox } from "@/lib/crew-demo";
import { inboxStore, useInbox } from "@/lib/crew-inbox";
import { placeLabel, slotLabel } from "@/lib/events";
import type { Card } from "@/lib/schemas";
import { CrewChat } from "./crew-chat";
import { DemoNote } from "./demo-note";
import { JoinCrewButton } from "./join-crew-button";

const route = getRouteApi("/_app/wydarzenie/$id_/ekipa");

// Telefon: pełny ekran nad nagłówkiem i dolnym paskiem (pole wiadomości zawsze na dole, z bezpiecznym
// obszarem). Desktop: karta w treści strony na wysokość okna minus nagłówek i odstępy <main>.
const shell =
  "fixed inset-0 z-30 flex flex-col overflow-hidden bg-background pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] " +
  "md:static md:z-auto md:mx-auto md:h-[calc(100dvh-10.5rem)] md:min-h-[520px] md:w-full md:max-w-[720px] md:rounded-2xl md:border md:bg-card md:p-0";

export function CrewChatScreen() {
  const { id } = route.useParams();
  const detail = useEvent(id);
  // Zapas jak w szczegółach: karta z cache rekomendacji, gdy GET /api/events/{id} zawiedzie.
  const fallback = useEventCard(id, detail.isError);
  const attendees = useAttendees(id);
  const card = detail.data ?? fallback.found?.card ?? null;
  const joined = attendees.data?.saved ?? card?.saved === true;
  // Skład ustalamy po odpowiedzi listy zapisanych, żeby imiona nie zmieniały się w trakcie rozmowy.
  const membersReady = attendees.data !== undefined || attendees.isError;
  const members = memberNames(crewMembers(attendees.data?.people, DEMO_CREW.names, DEMO_CREW.capacity - 1));
  const inbox = useInbox();
  const chatOpen = Boolean(card && membersReady && joined);

  // Otwarty czat = wszystko przeczytane (plakietki na „Twoje” i w nawigacji znikają). DEMO: lib/crew-inbox.ts.
  useEffect(() => {
    if (chatOpen) inboxStore.markRead(id);
  }, [chatOpen, id]);

  let body: ReactNode;
  if (card && chatOpen) {
    body = (
      <CrewChat
        // key: inne wydarzenie = nowa ekipa i świeży stan czatu
        key={id}
        members={members}
        seed={demoInbox(members, id, inbox[id]?.arrived ?? 0)}
        myLabel={ownLabel(currentName())}
        category={CATEGORY_LABEL[categoryOf(card.tags)]}
        place={placeLabel(card)}
        when={slotLabel(card.slot, new Date())}
      />
    );
  } else if (card && membersReady) {
    body = <JoinGate id={id} />;
  } else if (detail.isError && fallback.error) {
    body = (
      <div className="p-4">
        <RouteError
          message={errorText(detail.error, "Nie udało się pobrać wydarzenia.")}
          onRetry={() => {
            void detail.refetch();
            void fallback.refetch();
          }}
        />
      </div>
    );
  } else if (detail.isError && !fallback.isPending && !card) {
    body = <p className="p-4 text-meta text-muted-foreground">Nie znaleziono tego wydarzenia.</p>;
  } else {
    body = <Skeleton className="m-4 flex-1 rounded-2xl" />;
  }

  return (
    <section aria-labelledby="crew-title" className={shell}>
      <TopBar id={id} card={card} members={joined && membersReady ? members : null} />
      <DemoNote className="border-b bg-warning-soft px-4 py-2" />
      {body}
    </section>
  );
}

function TopBar({ id, card, members }: { id: string; card: Card | null; members: string[] | null }) {
  return (
    <header className="flex items-center gap-2 border-b bg-background px-2 py-2 md:bg-card">
      <Button asChild variant="ghost" size="icon" aria-label="Wróć do wydarzenia">
        <Link to="/wydarzenie/$id" params={{ id }}>
          <Icon name="arrow_back" size={24} />
        </Link>
      </Button>
      <div className="flex min-w-0 flex-1 flex-col">
        <h1 id="crew-title" className="truncate text-title font-bold">
          {card ? `Ekipa: ${card.title}` : "Ekipa"}
        </h1>
        {members && <p className="truncate text-sm text-muted-foreground">{membersLine(members)}</p>}
      </div>
      {members && (
        <Badge variant="success" size="lg" className="mr-2">
          <Icon name="group" size={18} />
          {members.length + 1}/{DEMO_CREW.capacity} osoby
        </Badge>
      )}
    </header>
  );
}

/** Niezapisani widzą zamiast czatu prośbę o zapis (po zapisie czat pojawia się od razu). */
function JoinGate({ id }: { id: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 bg-secondary p-6 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-primary-soft text-primary-ink">
        <Icon name="lock" size={28} />
      </span>
      <h2 className="text-title font-bold">Czat jest dla zapisanych</h2>
      <p className="max-w-sm text-base text-pretty text-muted-foreground">
        Zapisz się na wydarzenie, a dołączysz do ekipy (do {DEMO_CREW.capacity} osób), która idzie razem.
      </p>
      <JoinCrewButton id={id} className="w-full max-w-sm" />
    </div>
  );
}
