import { getRouteApi, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttendees } from "@/hooks/use-attendees.query";
import { useCrew } from "@/hooks/use-crew.query";
import { useEvent } from "@/hooks/use-event.query";
import { useEventCard } from "@/hooks/use-event-card.query";
import { ApiRequestError } from "@/lib/api";
import { CATEGORY_LABEL, categoryOf } from "@/lib/categories";
import { CREW_CAPACITY, crewSizeLabel, membersLine, otherNames } from "@/lib/crew-chat";
import { placeLabel, slotLabel } from "@/lib/events";
import type { Card, Crew } from "@/lib/schemas";
import { CrewChat } from "./crew-chat";
import { JoinCrewButton } from "./join-crew-button";

const route = getRouteApi("/_app/wydarzenie/$id_/ekipa");

// Telefon: pełny ekran nad nagłówkiem i dolnym paskiem (pole wiadomości zawsze na dole, z bezpiecznym
// obszarem). Desktop: karta w treści strony na wysokość okna minus nagłówek i odstępy <main>.
const shell =
  "fixed inset-0 z-30 flex flex-col overflow-hidden bg-background pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] " +
  "md:static md:z-auto md:mx-auto md:h-[calc(100dvh-10.5rem)] md:min-h-[520px] md:w-full md:max-w-[720px] md:rounded-2xl md:border md:bg-card md:p-0";

const loading = <Skeleton className="m-4 flex-1 rounded-2xl" />;

export function CrewChatScreen() {
  const { id } = route.useParams();
  const detail = useEvent(id);
  // Zapas jak w szczegółach: karta z cache rekomendacji, gdy GET /api/events/{id} zawiedzie.
  const fallback = useEventCard(id, detail.isError);
  const attendees = useAttendees(id);
  const card = detail.data ?? fallback.found?.card ?? null;
  const joined = attendees.data?.saved ?? card?.saved === true;
  // Prośbę o zapis pokazujemy dopiero po odpowiedzi listy zapisanych (karta z cache może być nieaktualna).
  const savedKnown = attendees.data !== undefined || attendees.isError;
  // Czat (GET …/crew) tylko dla zapisanych: pierwsze wejście dołącza do ekipy.
  const crew = useCrew(id, Boolean(card) && joined);
  const notAttending = crew.error instanceof ApiRequestError && crew.error.code === "not_attending";

  let body: ReactNode;
  if (!card) {
    if (detail.isError && fallback.error) {
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
    } else if (detail.isError && !fallback.isPending) {
      body = <p className="p-4 text-meta text-muted-foreground">Nie znaleziono tego wydarzenia.</p>;
    } else {
      body = loading;
    }
  } else if (!joined || notAttending) {
    body = savedKnown || notAttending ? <JoinGate id={id} /> : loading;
  } else if (crew.data) {
    const info = { category: CATEGORY_LABEL[categoryOf(card.tags)], place: placeLabel(card) || null, when: slotLabel(card.slot, new Date()) };
    // key: inna ekipa (wyjście i ponowne dołączenie) = świeży stan okna czatu
    body = <CrewChat key={`${id}:${crew.data.crew}`} id={id} crew={crew.data} info={info} />;
  } else if (crew.isError) {
    body = (
      <div className="p-4">
        <RouteError message={errorText(crew.error, "Nie udało się wczytać czatu ekipy.")} onRetry={() => void crew.refetch()} />
      </div>
    );
  } else {
    body = loading;
  }

  return (
    <section aria-labelledby="crew-title" className={shell}>
      <TopBar id={id} card={card} crew={joined && !notAttending ? (crew.data ?? null) : null} />
      {body}
    </section>
  );
}

function TopBar({ id, card, crew }: { id: string; card: Card | null; crew: Crew | null }) {
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
        {crew && <p className="truncate text-sm text-muted-foreground">{membersLine(otherNames(crew.members))}</p>}
      </div>
      {crew && (
        <Badge variant="success" size="lg" className="mr-2">
          <Icon name="group" size={18} />
          {crewSizeLabel(crew.members.length, crew.capacity)}
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
        Zapisz się na wydarzenie, a dołączysz do ekipy (do {CREW_CAPACITY} osób), która idzie razem.
      </p>
      <JoinCrewButton id={id} className="w-full max-w-sm" />
    </div>
  );
}
