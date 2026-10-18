import { Link } from "@tanstack/react-router";
import { SaveButton } from "@/components/community/save-button";
import { CrewChatRow } from "@/components/crew/crew-chat-row";
import { FriendsLine } from "@/components/friends/friends-line";
import { EventImage } from "@/components/events/event-image";
import { POSTER_FIELD } from "@/components/events/poster-tone";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { categoryOf } from "@/lib/categories";
import { placeLabel, slotLabel } from "@/lib/events";
import { pastSlotLabel } from "@/lib/my-events";
import type { MyEvent } from "@/lib/schemas";
import { cn } from "@/lib/utils";

type Props = { card: MyEvent; now: Date };

/**
 * Wydarzenie na zakładce „Twoje” (zwarta wersja karty): miniatura, tytuł, termin i miejsce, „Zapisano”
 * (wypisanie od razu usuwa je z listy - useSave), „Szczegóły” i wiersz czatu ekipy.
 */
export function MyEventItem({ card, now }: Props) {
  const when = card.past ? pastSlotLabel(card.slot, now) : slotLabel(card.slot, now);
  const place = [placeLabel(card) || null, card.district].filter(Boolean).join(" · ");
  const category = categoryOf(card.tags);
  const to = "/wydarzenie/$id" as const;
  const params = { id: card.id };

  return (
    <Card>
      <div className="flex gap-3 p-4">
        {/* Miniatura to drugi link w to samo miejsce: tylko dla myszy, bez fokusu i czytnika. */}
        <Link to={to} params={params} tabIndex={-1} aria-hidden="true" className="shrink-0">
          <div className={cn("relative size-20 overflow-hidden", POSTER_FIELD[category], card.past && "opacity-70")}>
            <EventImage
              imageUrl={card.imageUrl}
              category={category}
              duotone
              lazy
              className="absolute inset-0 size-full"
            />
          </div>
        </Link>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <CardTitle className="line-clamp-2 text-base leading-snug md:text-title">
            <Link
              to={to}
              params={params}
              className="rounded-sm outline-none hover:text-primary-ink focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            >
              {card.title}
            </Link>
          </CardTitle>
          {when && (
            <span className="flex gap-1.5 text-meta text-muted-foreground">
              <Icon name={card.past ? "event_busy" : card.kind === "recurring" ? "event_repeat" : "schedule"} size={18} />
              {when}
            </span>
          )}
          {place && (
            <span className="flex gap-1.5 text-meta text-muted-foreground">
              <Icon name="location_on" size={18} />
              <span className="truncate">{place}</span>
            </span>
          )}
          {!card.past && <FriendsLine eventId={card.id} className="text-meta" />}
          {card.past && (
            <Badge variant="secondary" className="mt-1">
              Minione
            </Badge>
          )}
        </div>
      </div>
      <div className="flex gap-2 px-4 pb-4">
        <SaveButton id={card.id} saved={card.saved} saves={card.saves} className="flex-1 px-3" />
        <Button asChild variant="secondary" className="flex-1 px-3">
          <Link to={to} params={params}>
            <Icon name="info" />
            Szczegóły
          </Link>
        </Button>
      </div>
      <CrewChatRow id={card.id} />
    </Card>
  );
}
