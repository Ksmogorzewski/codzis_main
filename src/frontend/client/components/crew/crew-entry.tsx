import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { DEMO_CREW } from "@/lib/crew-demo";

// Wejście do czatu ekipy zaraz pod tytułem wydarzenia — widoczne bez przewijania, także na telefonie.
export function CrewEntry({ eventId }: { eventId: string }) {
  return (
    <Card className="flex-row flex-wrap items-center gap-3 border-primary-soft bg-primary-soft p-4">
      <span className="flex size-12 items-center justify-center rounded-full bg-card text-primary-ink">
        <Icon name="groups" size={26} filled />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <h2 className="text-lg leading-tight font-bold">Ekipa na to wydarzenie</h2>
        <p className="text-meta text-muted-foreground">
          {DEMO_CREW.members}/{DEMO_CREW.capacity} osoby · odpowiedz na lodołamacz i dołącz do czatu
        </p>
      </div>
      <Button asChild className="w-full sm:w-auto">
        <Link to="/wydarzenie/$id/ekipa" params={{ id: eventId }}>
          <Icon name="forum" size={22} filled />
          Wejdź na czat
        </Link>
      </Button>
    </Card>
  );
}
