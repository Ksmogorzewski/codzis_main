import { getRouteApi, Link } from "@tanstack/react-router";
import { useEffect } from "react";
import { GRID } from "@/components/events/card-skeleton";
import { EventCard } from "@/components/events/event-card";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { usePopular } from "@/hooks/use-popular.query";
import { rankLabel, weekLabel } from "@/lib/community";
import { startLocation, useLocation } from "@/lib/location";

const route = getRouteApi("/_app/popularne");

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2.5 border-2 border-dashed border-input px-5 py-8 text-center">
      <Icon name="bookmark_add" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Jeszcze nikt się nie zapisał — bądź pierwszy</p>
      <p className="max-w-md text-meta text-muted-foreground">Zapisz się na wydarzenie z najbliższych 7 dni, a pojawi się tutaj.</p>
      <Button asChild size="sm">
        <Link to="/eksploruj">Eksploruj wydarzenia</Link>
      </Button>
    </div>
  );
}

/** Popularne w najbliższym tygodniu (dziś + 6 dni): kolejność i liczniki z API (najwięcej zapisanych najpierw). */
export function PopularView() {
  // Loader czeka na pierwszą odpowiedź; po zapisie lista odświeża się sama (useSave unieważnia klucz).
  const initial = route.useLoaderData();
  const popular = usePopular();
  const data = popular.data ?? initial;
  const { position } = useLocation();
  const now = new Date();
  const week = weekLabel(data.window);

  useEffect(() => startLocation(), []);

  return (
    <>
      <PageHeader title="Popularne w najbliższym tygodniu">
        Na co zapisuje się najwięcej osób{week ? ` · ${week}` : ""}.
      </PageHeader>
      {data.items.length > 0 ? (
        <ol className={GRID} aria-label="Najpopularniejsze wydarzenia">
          {data.items.map((c, i) => (
            <li key={c.id} className="flex">
              <EventCard card={c} position={position} now={now} rank={rankLabel(i)} />
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState />
      )}
    </>
  );
}
