import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { useAttendees } from "@/hooks/use-attendees.query";
import { crewMembers, memberNames, membersLine } from "@/lib/crew-chat";
import { DEMO_CREW } from "@/lib/crew-demo";
import { DemoNote } from "./demo-note";
import { JoinCrewButton } from "./join-crew-button";

type Props = { id: string; saved: boolean | undefined };

/**
 * „Ekipa na to wydarzenie” w szczegółach, pod „Kto się wybiera”: zapisani wchodzą na czat, pozostali
 * dostają przycisk zapisu. Stan zapisu z listy zapisanych (ten sam cache co sekcja wyżej), zapas: karta.
 */
export function CrewEntry({ id, saved }: Props) {
  const attendees = useAttendees(id);
  const joined = attendees.data?.saved ?? saved === true;
  const others = memberNames(crewMembers(attendees.data?.people, DEMO_CREW.names, DEMO_CREW.capacity - 1));

  return (
    <Card className="gap-3 p-5">
      <h2 className="flex items-center gap-2 text-xl font-extrabold">
        <Icon name="forum" size={24} filled className="text-primary-ink" />
        Ekipa na to wydarzenie
      </h2>
      <p className="text-base text-pretty text-muted-foreground">
        {joined
          ? `${membersLine(others)}. Odpowiedz na lodołamacz i umówcie się na wspólne wyjście.`
          : `Nie masz z kim iść? Zapisani dostają ekipę do ${DEMO_CREW.capacity} osób i wspólny czat.`}
      </p>
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
      <DemoNote />
    </Card>
  );
}
