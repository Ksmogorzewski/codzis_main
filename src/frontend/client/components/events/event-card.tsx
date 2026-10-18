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

// Zdjęcie wysuwa się od dołu na pole plakatu (250 ms, wyhamowanie). Trzy wyzwalacze: najechanie myszą
// i fokus klawiatury (CSS), karta na środku ekranu dotykowego albo stuknięcie w plakat (data-active, usePhotoReveal).
const SHOWN = "group-hover/card:[clip-path:inset(0)] group-focus-within/card:[clip-path:inset(0)] group-data-[active=true]/card:[clip-path:inset(0)]";
const HIDDEN_WHEN_SHOWN = "group-hover/card:opacity-0 group-focus-within/card:opacity-0 group-data-[active=true]/card:opacity-0";

/**
 * Karta-plakat: pole w kolorze kategorii z wielką godziną w tle i tytułem w kroju plakatu (zdjęcie, jeśli jest,
 * odsłania się na polu plakatu w naturalnych kolorach; tytuł zostaje na pasku w kolorze kategorii), pod spodem miejsce, cena, odległość, „Zapisanych: N”, „Ola idzie” (znajomi,
 * GET /api/friends/going), „Pasuje: …” (tylko rekomendacje), Trasa / Zapisz / Szczegóły.
 * Pole plakatu rośnie, gdy karty w rzędzie mają różną wysokość. Ta sama karta na wszystkich listach.
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
  // pasek w kolorze kategorii pod tekstem: niewidoczny na polu plakatu, czytelny na zdjęciu
  const onPhoto = cn("box-decoration-clone px-1.5 -mx-1.5", POSTER_FIELD[category]);

  return (
    <Card ref={reveal.ref} data-active={reveal.active} className="group/card">
      {/* Stuknięcie w plakat (poza linkiem tytułu) przełącza zdjęcie; klawiatura dostaje je przez fokus tytułu. */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents lint/a11y/noStaticElementInteractions: zdjęcie jest ozdobą, fokus obsługuje CSS */}
      <div
        onClick={(e) => {
          if (!(e.target instanceof Element && e.target.closest("a"))) reveal.toggle();
        }}
        className={cn(
          "relative flex min-h-[200px] flex-1 flex-col gap-3 overflow-hidden border-b-2 border-input px-4 pt-4 pb-5",
          POSTER_FIELD[category],
        )}
      >
        {hasPhoto && (
          <EventImage
            imageUrl={card.imageUrl}
            category={category}
            lazy
            onFailed={() => setPhotoFailed(true)}
            className={cn(
              "absolute inset-0 [clip-path:inset(100%_0_0_0)] motion-safe:transition-[clip-path] motion-safe:duration-[250ms] motion-safe:ease-[cubic-bezier(.16,1,.3,1)]",
              SHOWN,
            )}
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
        <div className="relative flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[13px] leading-tight font-bold tracking-[0.1em] uppercase">
          {rank && (
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-foreground text-sm font-extrabold text-background tabular-nums">
              <span className="sr-only">Miejsce </span>
              {rank}
            </span>
          )}
          <span className={onPhoto}>
            {CATEGORY_LABEL[category]}
            {when && ` · ${when}`}
          </span>
          <EventBadges card={card} />
        </div>
        <h3 className="relative font-display text-[32px] leading-[0.95] font-bold text-pretty uppercase [font-stretch:68%] md:text-[34px]">
          <Link
            to={to}
            params={params}
            className="outline-none decoration-2 underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-current"
          >
            <span className={onPhoto}>{card.title}</span>
          </Link>
        </h3>
      </div>
      <div className="flex flex-col gap-2 p-4">
        {(place || price) && (
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-meta text-muted-foreground">{place}</span>
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
