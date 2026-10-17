import { getRouteApi, Link } from "@tanstack/react-router";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { useEventCard } from "@/hooks/use-event-card.query";
import { CATEGORY_LABEL, categoryOf } from "@/lib/categories";
import { lastSearch } from "@/lib/search";
import { CrewChat } from "./crew-chat";

const route = getRouteApi("/_app/wydarzenie/$id_/ekipa");

// Wysokość ekranu minus nagłówek portalu, odstępy <main> i przycisk powrotu: czat na cały ekran jak w mockupie.
const fullHeight = "h-[calc(100dvh-11.5rem)] min-h-[460px] md:h-[calc(100dvh-14rem)]";

export function CrewChatScreen() {
  const { id } = route.useParams();
  const { found, isPending, error, refetch } = useEventCard(id);

  return (
    <div className="mx-auto flex w-full max-w-[640px] flex-col gap-4">
      <Button asChild variant="secondary" size="sm" className="self-start pr-3.5 pl-2 font-semibold">
        {found ? (
          <Link to="/wydarzenie/$id" params={{ id }}>
            <Icon name="chevron_left" size={22} />
            Wydarzenie
          </Link>
        ) : (
          <Link to="/" search={lastSearch()}>
            <Icon name="chevron_left" size={22} />
            Rekomendacje
          </Link>
        )}
      </Button>
      {found ? (
        <CrewChat
          // key: inne wydarzenie = nowa ekipa i świeży stan czatu
          key={id}
          eventTitle={found.card.title}
          category={CATEGORY_LABEL[categoryOf(found.card.tags)]}
          className={fullHeight}
        />
      ) : error ? (
        <RouteError message={errorText(error, "Nie udało się pobrać wydarzenia.")} onRetry={() => void refetch()} />
      ) : isPending ? (
        <Skeleton className={`${fullHeight} rounded-2xl`} />
      ) : (
        <p className="text-meta text-muted-foreground">Nie znaleziono tego wydarzenia – wróć do rekomendacji.</p>
      )}
    </div>
  );
}
