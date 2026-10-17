import { Link } from "@tanstack/react-router";
import { SaveButton, SavesCount } from "@/components/community/save-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { mapsUrl, placeLabel, priceLabel, slotLabel } from "@/lib/events";
import { type Point, walkLabel } from "@/lib/geo";
import type { Card as CardData } from "@/lib/schemas";
import { EventBadges } from "./event-badges";
import { EventImage } from "./event-image";

type Props = {
  card: CardData;
  position: Point | null;
  now: Date;
  /** Miejsce na liście Popularnych (od 1); bez niego karta bez numeru. */
  rank?: string;
};

/**
 * Karta wydarzenia (mockup 1a): zdjęcie, tytuł, cena, termin, miejsce, odległość, „Zapisanych: N”,
 * „Pasuje: …” (tylko rekomendacje), Trasa / Zapisz / Szczegóły. Ta sama karta na wszystkich listach.
 * Nawigacja to prawdziwe linki (Ctrl/Cmd+klik otwiera nową kartę).
 */
export function EventCard({ card, position, now, rank }: Props) {
  const price = priceLabel(card);
  const when = slotLabel(card.slot, now);
  const place = [placeLabel(card) || null, card.district].filter(Boolean).join(" · ");
  const dist = walkLabel(position, card.location);
  const route = mapsUrl(card);
  const to = "/wydarzenie/$id" as const;
  const params = { id: card.id };

  return (
    <Card>
      {/* Zdjęcie to drugi link w to samo miejsce: tylko dla myszy, bez fokusu i czytnika. */}
      <Link to={to} params={params} tabIndex={-1} aria-hidden="true">
        <EventImage id={card.id} imageUrl={card.imageUrl} stripe={10} lazy className="h-[168px]">
          <EventBadges card={card} />
        </EventImage>
      </Link>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2.5">
          {rank && (
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-base font-extrabold text-primary-foreground tabular-nums">
              <span className="sr-only">Miejsce </span>
              {rank}
            </span>
          )}
          <CardTitle className="flex-1">
            <Link
              to={to}
              params={params}
              className="rounded-sm outline-none hover:text-primary-ink focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            >
              {card.title}
            </Link>
          </CardTitle>
          {price && (
            <Badge variant={price.free ? "success" : "secondary"} size="price">
              {price.label}
            </Badge>
          )}
        </div>
        <div className="flex flex-col gap-1 text-meta text-muted-foreground">
          {when && (
            <span className="flex gap-1.5">
              <Icon name={card.kind === "recurring" ? "event_repeat" : "schedule"} size={18} />
              {when}
            </span>
          )}
          {place && (
            <span className="flex gap-1.5">
              <Icon name="location_on" size={18} />
              {place}
            </span>
          )}
          {dist && (
            <span className="flex gap-1.5 font-semibold text-foreground">
              <Icon name="directions_walk" size={18} />
              {dist}
            </span>
          )}
          <SavesCount saves={card.saves} />
        </div>
        {card.reason && (
          <p className="flex gap-2 rounded-[14px] bg-secondary px-3 py-2.5 text-meta leading-snug">
            <Icon name="check_circle" size={18} filled className="text-primary-ink" />
            <span>
              <b className="text-primary-ink">Pasuje:</b> {card.reason}
            </span>
          </p>
        )}
        <div className="mt-auto flex gap-2">
          {route && (
            <Button asChild variant="outline" size="icon" className="size-12">
              <a href={route} target="_blank" rel="noopener noreferrer" aria-label="Trasa" title="Trasa">
                <Icon name="directions" size={22} />
              </a>
            </Button>
          )}
          <SaveButton id={card.id} saved={card.saved} saves={card.saves} className="flex-1 px-3" />
          <Button asChild className="flex-1 px-3">
            <Link to={to} params={params}>
              <Icon name="info" />
              Szczegóły
            </Link>
          </Button>
        </div>
      </div>
    </Card>
  );
}
