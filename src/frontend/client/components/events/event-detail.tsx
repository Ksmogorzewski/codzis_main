import { getRouteApi, Link, useCanGoBack, useRouter } from "@tanstack/react-router";
import { type ReactNode, useEffect } from "react";
import { AttendeesSection } from "@/components/community/attendees-section";
import { SaveButton, SavesCount } from "@/components/community/save-button";
import { CrewEntry } from "@/components/crew/crew-entry";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Separator } from "@/components/ui/separator";
import { useEvent } from "@/hooks/use-event.query";
import { useEventCard } from "@/hooks/use-event-card.query";
import { useMe } from "@/hooks/use-me.query";
import { CATEGORY_LABEL, categoryOf } from "@/lib/categories";
import { config } from "@/lib/config";
import {
  mapsUrl,
  outboundLink,
  placeLabel,
  posterTime,
  priceLabel,
  readAtLabel,
  safeUrl,
  scheduleLabels,
  slotLabel,
  sourceLabel,
} from "@/lib/events";
import { walkLabel } from "@/lib/geo";
import { startLocation, useLocation } from "@/lib/location";
import { destinationOf, districtOf, mapsEmbedUrl, originOf } from "@/lib/maps";
import type { Card as CardData, EventDetail } from "@/lib/schemas";
import { lastSearch } from "@/lib/search";
import { tagChips } from "@/lib/tags";
import { cn } from "@/lib/utils";
import { DetailSkeleton } from "./detail-skeleton";
import { EventBadges } from "./event-badges";
import { EventImage } from "./event-image";
import { POSTER_FIELD, POSTER_SHADE } from "./poster-tone";
import { RouteMap } from "./route-map";

const route = getRouteApi("/_app/wydarzenie/$id");

const backClass = "self-start pr-3.5 pl-2 font-semibold";

/** Wróć tam, skąd przyszliśmy (Dla Ciebie, Eksploruj, Popularne); z linku z zewnątrz - do propozycji. */
function BackLink() {
  const router = useRouter();
  const canGoBack = useCanGoBack();
  if (canGoBack) {
    return (
      <Button variant="outline" size="sm" className={backClass} onClick={() => router.history.back()}>
        <Icon name="chevron_left" size={22} />
        Wróć
      </Button>
    );
  }
  return (
    <Button asChild variant="outline" size="sm" className={backClass}>
      <Link to="/" search={lastSearch()}>
        <Icon name="chevron_left" size={22} />
        Dla Ciebie
      </Link>
    </Button>
  );
}

function Fact({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-full flex flex-col gap-0.5" : "flex flex-col gap-0.5"}>
      <dt className="text-[13px] font-bold tracking-[0.1em] text-muted-foreground uppercase">{label}</dt>
      <dd className="text-lg font-bold">{children}</dd>
    </div>
  );
}

function NotFound() {
  return (
    <>
      <BackLink />
      <div className="flex flex-col items-center gap-2.5 border-2 border-dashed border-input px-5 py-8 text-center">
        <Icon name="search_off" size={40} className="text-muted-foreground" />
        <h1 className="font-display text-[30px] leading-[0.95] font-black text-balance uppercase [font-stretch:66%]">
          Nie znaleziono tego wydarzenia
        </h1>
        <p className="max-w-md text-meta text-muted-foreground">
          Mogło się już zakończyć albo zniknąć z kalendarza miasta.
        </p>
        <Button asChild size="sm">
          <Link to="/eksploruj">Eksploruj wydarzenia</Link>
        </Button>
      </div>
    </>
  );
}

/** Kolejne terminy wydarzenia (bez tych, które już minęły), najwyżej 6. */
function upcoming(occurrences: EventDetail["occurrences"], now: Date): EventDetail["occurrences"] {
  return occurrences.filter((o) => new Date(o.end ?? o.start) >= now).slice(0, 6);
}

type DetailProps = { card: CardData; builtAt: string | null; detail?: EventDetail };

function Detail({ card, builtAt, detail }: DetailProps) {
  const { position, status } = useLocation();
  const me = useMe();
  const district = districtOf(me.data?.profile?.preferences);
  // Mapa z trasą komunikacją: start z lokalizacji (gdy jest zgoda), inaczej z dzielnicy z profilu
  const origin = originOf(position, district);
  const mapSrc = mapsEmbedUrl({ key: config().mapsEmbedKey, origin, destination: destinationOf(card) });
  const mapCaption = position
    ? "Trasa komunikacją miejską z Twojej lokalizacji"
    : origin
      ? `Trasa komunikacją miejską z dzielnicy ${district}`
      : "Miejsce wydarzenia na mapie";
  const now = new Date();
  const when = slotLabel(card.slot, now);
  const plan = scheduleLabels(card.schedule);
  const price = priceLabel(card);
  const place = placeLabel(card);
  const dist = walkLabel(position, card.location);
  const route = mapsUrl(card);
  const link = outboundLink(card);
  const page = safeUrl(card.url);
  const readAt = readAtLabel(detail?.importedAt ?? builtAt);
  const description = detail?.text || card.lead;
  const dates = detail ? upcoming(detail.occurrences, now) : [];
  const chips = tagChips(card.tags);
  const category = categoryOf(card.tags);
  const clock = posterTime(card.slot);
  const distance = card.online
    ? "Online"
    : (dist ?? (status === "denied" ? "Włącz lokalizację, aby zobaczyć" : card.location ? "—" : "Brak współrzędnych"));

  return (
    <article className="flex flex-col gap-4 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-4 motion-safe:duration-[250ms]">
      <BackLink />
      {/* Nagłówek-plakat w kolorze kategorii, jak karta na liście; zdjęcie (jeśli jest) pod nim w naturalnych kolorach. */}
      <header
        className={cn(
          "relative flex flex-col gap-3 overflow-hidden border-2 border-input px-5 pt-5 pb-6 md:px-8 md:pt-7 md:pb-9",
          POSTER_FIELD[category],
        )}
      >
        {clock && (
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute -right-3 -bottom-12 font-display text-[180px] leading-none font-black tracking-[-0.02em] select-none [font-stretch:60%] md:-bottom-20 md:text-[300px]",
              POSTER_SHADE[category],
            )}
          >
            {clock}
          </span>
        )}
        <div className="relative flex flex-wrap items-center gap-x-2.5 gap-y-2 text-[13px] leading-tight font-bold tracking-[0.1em] uppercase md:text-sm">
          <span>
            {CATEGORY_LABEL[category]}
            {when && ` · ${when}`}
          </span>
          <EventBadges card={card} large />
        </div>
        <h1 className="relative max-w-[16ch] font-display text-[44px] leading-[0.92] font-black text-pretty uppercase [font-stretch:62%] md:text-[76px]">
          {card.title}
        </h1>
        {(place || card.district) && (
          <p className="relative text-[17px] font-semibold">{[place, card.district].filter(Boolean).join(" · ")}</p>
        )}
        {chips.length > 0 && (
          <div className="relative mt-1 flex flex-wrap gap-1.5" aria-label="Tagi">
            {chips.map((chip) => (
              <Badge key={chip} variant="surface" size="lg" className="tracking-[0.06em] uppercase">
                {chip}
              </Badge>
            ))}
          </div>
        )}
      </header>

      <EventImage
        imageUrl={card.imageUrl}
        category={category}
        fit="contain"
        className="h-60 border-2 border-input md:h-[400px]"
      />

      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          {/* Opis z API jest już tekstem (HTML usuwa backend) - bez dangerouslySetInnerHTML. */}
          {description && <p className="text-lg leading-relaxed text-pretty whitespace-pre-line">{description}</p>}
          {card.reason && (
            <Card className="gap-3 p-5">
              <h2 className="font-display text-2xl leading-none font-extrabold [font-stretch:90%]">Dlaczego to polecamy</h2>
              <p className="text-[17px] leading-snug">
                <b>Pasuje:</b> {card.reason}
              </p>
            </Card>
          )}
          <AttendeesSection id={card.id} />
          <CrewEntry id={card.id} saved={card.saved} />
        </div>

        {/* Karta z faktami obok treści i mapy (na telefonie: przed mapą) */}
        <Card className="md:row-span-2">
          <dl className="grid grid-cols-2 gap-4 p-5">
            <Fact label="Termin" wide>
              {when ?? "—"}
            </Fact>
            {plan.length > 0 && (
              <Fact label="Co tydzień" wide>
                <ul className="flex flex-wrap gap-x-3 gap-y-0.5">
                  {plan.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </Fact>
            )}
            {dates.length > 1 && (
              <Fact label="Kolejne terminy" wide>
                <ul className="flex flex-col gap-0.5 text-base font-semibold">
                  {dates.map((o) => (
                    <li key={o.start}>{slotLabel(o, now)}</li>
                  ))}
                </ul>
              </Fact>
            )}
            <Fact label="Cena">{price?.label ?? "—"}</Fact>
            <Fact label="Odległość">{distance}</Fact>
          </dl>
          <Separator />
          <div className="flex flex-col gap-2.5 p-4">
            <SaveButton id={card.id} saved={card.saved} saves={card.saves} size="lg" />
            <SavesCount saves={card.saves} className="justify-center text-meta text-muted-foreground" />
          </div>
          {(route || link) && (
            <>
              <Separator />
              <div className="flex flex-col gap-2.5 p-4">
                {route && (
                  <Button asChild variant="outline" size="lg">
                    <a href={route} target="_blank" rel="noopener noreferrer">
                      <Icon name={mapSrc ? "open_in_new" : "directions"} size={22} />
                      {mapSrc ? "Otwórz w Mapach Google" : "Wyznacz trasę"}
                    </a>
                  </Button>
                )}
                {link && (
                  <Button asChild variant="brand" size="lg">
                    <a href={link.href} target="_blank" rel="noopener noreferrer">
                      <Icon name={link.kind === "ticket" ? "confirmation_number" : "open_in_new"} size={22} />
                      {link.label}
                    </a>
                  </Button>
                )}
              </div>
            </>
          )}
        </Card>

        {mapSrc && <RouteMap src={mapSrc} eventTitle={card.title} caption={mapCaption} className="md:col-start-1" />}
      </div>

      <footer className="text-sm text-muted-foreground">
        Źródło:{" "}
        {page ? (
          <a
            href={page}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-sm underline underline-offset-2 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring"
          >
            {sourceLabel(card)}
          </a>
        ) : (
          sourceLabel(card)
        )}
        {readAt && ` · dane z ${readAt}`}
      </footer>
    </article>
  );
}

export function EventDetailView() {
  const { id } = route.useParams();
  const detail = useEvent(id);
  // Zapas: karta z cache rekomendacji, gdy szczegóły z API się nie udały (np. backend jeszcze bez trasy).
  const fallback = useEventCard(id, detail.isError);

  useEffect(() => startLocation(), []);

  if (detail.data) {
    const full = detail.isPlaceholderData ? undefined : detail.data;
    return <Detail card={detail.data} builtAt={null} detail={full} />;
  }
  if (!detail.isError) return <Loading />;
  if (fallback.found) return <Detail card={fallback.found.card} builtAt={fallback.found.builtAt} />;
  if (fallback.isPending) return <Loading coldStart={fallback.coldStart} />;
  if (fallback.error) {
    return (
      <>
        <BackLink />
        <RouteError
          message={errorText(detail.error, "Nie udało się pobrać wydarzenia.")}
          onRetry={() => {
            void detail.refetch();
            void fallback.refetch();
          }}
        />
      </>
    );
  }
  return <NotFound />;
}

function Loading({ coldStart = false }: { coldStart?: boolean }) {
  return (
    <>
      <BackLink />
      <p role="status" className="flex items-center gap-2 text-meta text-muted-foreground">
        <Icon name="progress_activity" size={18} className="motion-safe:animate-spin" />
        {coldStart ? "Dobieramy propozycje… Za pierwszym razem może to potrwać do pół minuty." : "Wczytujemy wydarzenie…"}
      </p>
      <DetailSkeleton />
    </>
  );
}
