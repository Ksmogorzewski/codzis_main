import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { SaveButton, SavesCount } from "@/components/community/save-button";
import { FriendsLine } from "@/components/friends/friends-line";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { CATEGORY_LABEL, categoryOf } from "@/lib/categories";
import { usePhotoReveal } from "@/hooks/use-photo-reveal";
import { mapsUrl, placeLabel, posterTime, priceLabel, safeUrl, slotLabel } from "@/lib/events";
import { type Point, walkLabel } from "@/lib/geo";
import type { Card as CardData } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { EventBadges } from "./event-badges";
import { EventImage } from "./event-image";
import { HIDDEN_WHEN_SHOWN, PHOTO_REVEAL } from "./photo-reveal";
import { POSTER_FIELD, POSTER_SHADE } from "./poster-tone";

type Props = {
  card: CardData;
  position: Point | null;
  now: Date;
  /** Miejsce na liście Popularnych (od 1); bez niego karta bez numeru. */
  rank?: string;
  /** Podpis przycisku zapisu (na „Znajomi idą”: „Idę też”). */
  saveLabel?: string;
};

/**
 * Karta-plakat: pole w kolorze kategorii z wielką godziną w tle i tytułem w kroju plakatu (zdjęcie, jeśli jest,
 * odsłania się na polu plakatu w naturalnych kolorach; tytuł zostaje na pasku w kolorze kategorii), pod spodem miejsce, cena, odległość, „Zapisanych: N”, „Ola idzie” (znajomi,
 * GET /api/friends/going), „Pasuje: …” (tylko rekomendacje), Trasa / Zapisz / Szczegóły.
 * Pole plakatu ma stałą wysokość (tytuł maks. 3 linie, jeden temat bez pod dachem / plener), biała część wypełnia
 * resztę karty - w rzędzie kart oba pola są równe. Ta sama karta na wszystkich listach.
 * Nawigacja to prawdziwe linki (Ctrl/Cmd+klik otwiera nową kartę).
 */
export function EventCard({ card, position, now, rank, saveLabel }: Props) {
  const category = categoryOf(card.tags);
  const price = priceLabel(card);
  const when = slotLabel(card.slot, now);
  const clock = posterTime(card.slot);
  const place = [placeLabel(card) || null, card.district].filter(Boolean).join(" · ");
  const dist = walkLabel(position, card.location);
  const route = mapsUrl(card);
  const to = "/wydarzenie/$id" as const;
  const params = { id: card.id };
  const [photoFailed, setPhotoFailed] = useState(false);
  const hasPhoto = safeUrl(card.imageUrl) !== null && !photoFailed;
  const reveal = usePhotoReveal<HTMLDivElement>(hasPhoto);
  // Pasek w kolorze kategorii pod tekstem: niewidoczny na polu plakatu, czytelny na zdjęciu. Wszystkie paski
  // (nadtytuł, temat, linie tytułu) mają tę samą lewą krawędź i odstęp px-2; pole ma px-2, więc tekst stoi tam,
  // gdzie przy px-4, a paski wchodzą w margines.
  const onPhoto = cn("box-decoration-clone px-2", POSTER_FIELD[category]);

  return (
    <Card ref={reveal.ref} data-active={reveal.active} className="group/poster">
      {/* Stuknięcie w plakat (poza linkiem tytułu) przełącza zdjęcie; klawiatura dostaje je przez fokus tytułu. */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents lint/a11y/noStaticElementInteractions: zdjęcie jest ozdobą, fokus obsługuje CSS */}
      {/* overflow-clip, nie hidden: godzina w tle wystaje poza pole, a z overflow-hidden fokus tytułu (scrollIntoView)
          przewijał pole i zdjęcie odsłaniało się przesunięte */}
      <div
        onClick={(e) => {
          if (!(e.target instanceof Element && e.target.closest("a"))) reveal.toggle();
        }}
        className={cn(
          "relative flex h-[232px] shrink-0 flex-col gap-2.5 overflow-clip border-b-2 border-input px-2 pt-4 pb-4",
          POSTER_FIELD[category],
        )}
      >
        {hasPhoto && (
          <EventImage
            imageUrl={card.imageUrl}
            category={category}
            lazy
            onFailed={() => setPhotoFailed(true)}
            className={PHOTO_REVEAL}
          />
        )}
        {clock && (
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute -right-2 -bottom-10 font-display text-[150px] leading-none font-black tracking-[-0.02em] select-none [font-stretch:60%]",
              POSTER_SHADE[category],
              hasPhoto && cn("motion-safe:transition-opacity motion-safe:duration-150", HIDDEN_WHEN_SHOWN),
            )}
          >
            {clock}
          </span>
        )}
        {hasPhoto && (
          <span
            aria-hidden="true"
            className={cn(
              "absolute right-3 bottom-3 grid size-8 place-items-center bg-card text-foreground motion-safe:transition-opacity motion-safe:duration-150",
              HIDDEN_WHEN_SHOWN,
            )}
          >
            <Icon name="photo_camera" size={18} />
          </span>
        )}
        <div className="relative flex flex-wrap items-center gap-1.5 text-[13px] font-bold tracking-[0.1em] uppercase">
          {rank && (
            <span className="ml-2 grid size-7 shrink-0 place-items-center rounded-full bg-foreground text-sm font-extrabold text-background tabular-nums">
              <span className="sr-only">Miejsce </span>
              {rank}
            </span>
          )}
          {/* wysokość jak naklejka tematu (Badge: py-[5px], leading-none), żeby paski w rzędzie się zgadzały */}
          <span className={cn(onPhoto, "py-[5px] leading-none")}>
            {CATEGORY_LABEL[category]}
            {when && ` · ${when}`}
          </span>
          <EventBadges card={card} setting={false} />
        </div>
        <h3 className="relative line-clamp-3 font-display text-[32px] leading-[1.08] font-bold text-pretty uppercase [font-stretch:68%] md:text-[34px]">
          <Link
            to={to}
            params={params}
            className="outline-none decoration-2 underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-current"
          >
            <span className={onPhoto}>{card.title}</span>
          </Link>
        </h3>
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        {(place || price) && (
          <div className="flex items-baseline justify-between gap-3">
            <span className="line-clamp-2 text-meta text-muted-foreground">{place}</span>
            {price && (
              <span
                className={cn(
                  "font-display text-[22px] leading-none font-bold whitespace-nowrap [font-stretch:80%]",
                  price.free && "text-success-ink",
                )}
              >
                {price.label}
              </span>
            )}
          </div>
        )}
        {dist && <span className="text-meta font-bold">{dist}</span>}
        <div className="flex flex-col gap-1 text-meta text-muted-foreground">
          <SavesCount saves={card.saves} />
          <FriendsLine eventId={card.id} />
        </div>
        {card.reason && (
          <p className="mt-1 border-t pt-2.5 text-meta leading-snug">
            <b>Pasuje:</b> {card.reason}
          </p>
        )}
        {/* Na 360 px trzy przyciski mieszczą się tylko bez ikony „Szczegóły” i z mniejszym marginesem. */}
        <div className="mt-auto flex gap-2 pt-2">
          {route && (
            <Button asChild variant="outline" size="icon" className="size-12">
              <a href={route} target="_blank" rel="noopener noreferrer" aria-label="Trasa" title="Trasa">
                <Icon name="directions" size={22} />
              </a>
            </Button>
          )}
          <SaveButton
            id={card.id}
            saved={card.saved}
            saves={card.saves}
            label={saveLabel}
            className="min-w-0 flex-1 px-3 max-[380px]:px-2"
          />
          <Button asChild className="min-w-0 flex-1 px-3 max-[380px]:px-2">
            <Link to={to} params={params}>
              {/* ukrywa opakowanie: arkusz Material Symbols (poza warstwami) wygrywa z „hidden” na samej ikonie */}
              <span className="flex max-[380px]:hidden">
                <Icon name="info" />
              </span>
              Szczegóły
            </Link>
          </Button>
        </div>
      </div>
    </Card>
  );
}
