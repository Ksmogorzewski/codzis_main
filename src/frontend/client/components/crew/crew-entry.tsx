import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { useAttendees } from "@/hooks/use-attendees.query";
import { useMyCrews } from "@/hooks/use-my-crews.query";
import { CREW_CAPACITY, membersLine, otherNames } from "@/lib/crew-chat";
import type { MyCrew } from "@/lib/schemas";
import { JoinCrewButton } from "./join-crew-button";

type Props = { id: string; saved: boolean | undefined };

function entryText(joined: boolean, crew: MyCrew | undefined): string {
  if (!joined) return `Nie masz z kim iść? Zapisani dostają ekipę do ${CREW_CAPACITY} osób i wspólny czat.`;
  if (!crew) return `Wejdź na czat, a dołączysz do ekipy do ${CREW_CAPACITY} osób, która idzie razem.`;
  const others = otherNames(crew.members);
  if (others.length === 0) return "Na razie w ekipie jesteś tylko Ty – kolejne osoby dołączą, gdy się zapiszą i wejdą na czat.";
  return `${membersLine(others)}. Umówcie się na czacie na wspólne wyjście.`;
}

/**
 * „Ekipa na to wydarzenie” w szczegółach, pod „Kto się wybiera”: zapisani wchodzą na czat (skład ekipy
 * z GET /api/me/crews), pozostali dostają przycisk zapisu. Stan zapisu z listy zapisanych (ten sam cache co
 * sekcja wyżej), zapas: karta.
 */
export function CrewEntry({ id, saved }: Props) {
  const attendees = useAttendees(id);
  const joined = attendees.data?.saved ?? saved === true;
  const crew = useMyCrews().data?.items.find((c) => c.eventId === id);

  return (
    <Card className="gap-3 bg-secondary p-5">
      <h2 className="flex items-center gap-2 text-xl font-extrabold">
        <Icon name="forum" size={24} filled className="text-primary-ink" />
        Ekipa na to wydarzenie
      </h2>
      <p className="text-base text-pretty text-muted-foreground">{entryText(joined, crew)}</p>
      {joined ? (
        <Button asChild size="lg">
          <Link to="/wydarzenie/$id/ekipa" params={{ id }}>
            <Icon name="forum" size={22} filled />
            Wejdź na czat
          </Link>
        </Button>
      ) : (
        <JoinCrewButton id={id} />
      )}
    </Card>
  );
}
