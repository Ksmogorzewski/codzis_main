import { getRouteApi, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyEvents } from "@/hooks/use-my-events.query";
import { eventCountLabel } from "@/lib/events";
import { groupMyEvents } from "@/lib/my-events";
import type { MyEvent } from "@/lib/schemas";
import { MyEventItem } from "./my-event-item";

const route = getRouteApi("/_app/twoje");

const LIST = "grid grid-cols-1 gap-4 md:grid-cols-2";

/** Zakładka „Twoje”: wydarzenia, na które jestem zapisany (nadchodzące i minione), z czatami ekip. */
export function MyEventsView() {
  // Loader czeka na pierwszą odpowiedź; wypisanie usuwa wydarzenie od razu (useSave).
  const initial = route.useLoaderData();
  const mine = useMyEvents();
  const { upcoming, past } = groupMyEvents((mine.data ?? initial).items);
  const now = new Date();

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-[32px] leading-[1.05] font-extrabold tracking-[-0.03em] md:text-[40px]">Twoje wydarzenia</h1>
        <p className="text-lg text-muted-foreground">Na co się zapisujesz i czaty ekip, z którymi idziesz.</p>
      </header>
      {upcoming.length + past.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <Section id="upcoming" title="Nadchodzące" items={upcoming} now={now}>
            <p className="text-meta text-muted-foreground">
              Nic nie czeka w kalendarzu.{" "}
              <Link to="/eksploruj" className="font-bold text-brand-ink underline-offset-4 hover:underline">
                Znajdź coś w Eksploruj
              </Link>
            </p>
          </Section>
          {past.length > 0 && <Section id="past" title="Minione" items={past} now={now} />}
        </>
      )}
    </>
  );
}

type SectionProps = { id: string; title: string; items: MyEvent[]; now: Date; children?: ReactNode };

function Section({ id, title, items, now, children }: SectionProps) {
  return (
    <section aria-labelledby={`twoje-${id}`} className="flex flex-col gap-3">
      <h2 id={`twoje-${id}`} className="flex items-baseline gap-2 text-xl font-extrabold">
        {title}
        <span className="text-meta font-semibold text-muted-foreground">{eventCountLabel(items.length)}</span>
      </h2>
      {items.length > 0 ? (
        <ul className={LIST}>
          {items.map((c) => (
            <li key={c.id} className="flex min-w-0 flex-col">
              <MyEventItem card={c} now={now} />
            </li>
          ))}
        </ul>
      ) : (
        children
      )}
    </section>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2.5 rounded-2xl border-[1.5px] border-dashed border-input px-5 py-8 text-center">
      <Icon name="event_available" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Nie masz jeszcze zapisów</p>
      <p className="max-w-md text-meta text-muted-foreground">
        Zapisz się na wydarzenie, a pojawi się tutaj razem z czatem ekipy.
      </p>
      <Button asChild size="sm">
        <Link to="/eksploruj">Eksploruj wydarzenia</Link>
      </Button>
    </div>
  );
}

/** Szkielet listy na czas pierwszego ładowania. */
export function MyEventsSkeleton() {
  return (
    <>
      <Skeleton className="h-10 w-[60%]" />
      <div className={LIST} aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[232px] rounded-2xl" />
        ))}
      </div>
    </>
  );
}
