import { getRouteApi, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { GRID, GridSkeleton } from "@/components/events/card-skeleton";
import { CategoryFilter } from "@/components/events/category-filter";
import { EventCard } from "@/components/events/event-card";
import { SearchBox } from "@/components/events/search-box";
import { WhenFilter } from "@/components/events/when-filter";
import { PageHeader } from "@/components/layout/page-header";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useEvents } from "@/hooks/use-events.query";
import { useOnboarding } from "@/hooks/use-onboarding.query";
import {
  DEFAULT_EXPLORE,
  districtOptions,
  type EventsParams,
  type ExploreSearch,
  eventsParams,
  sortCards,
} from "@/lib/explore";
import { eventCountLabel } from "@/lib/events";
import { startLocation, useLocation } from "@/lib/location";
import { cn } from "@/lib/utils";

const route = getRouteApi("/_app/eksploruj");

/** Kart na raz; „Pokaż więcej” dokłada kolejne (lista bywa długa: ~1200 wydarzeń w bazie). */
const PAGE = 24;

const WHEN = [
  { id: "today", label: "Dziś" },
  { id: "tomorrow", label: "Jutro" },
  { id: "weekend", label: "Weekend" },
] as const;

type Go = (next: Partial<ExploreSearch>) => void;

type FiltersProps = { search: ExploreSearch; params: EventsParams; districts: string[]; go: Go };

function Filters({ search, params: { when, date }, districts, go }: FiltersProps) {
  const onQuery = useCallback((q: string) => go({ q }), [go]);
  const flags = [search.free && "free", search.indoor && "indoor"].filter((f): f is string => Boolean(f));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <WhenFilter
          options={WHEN}
          value={when}
          date={date}
          onWhen={(when) => go({ when, date: undefined })}
          onDate={(d) => go({ when: "date", date: d })}
        />
        <SearchBox value={search.q} onChange={onQuery} />
      </div>
      <CategoryFilter value={search.cat} onChange={(cat) => go({ cat })} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex min-w-0 items-center sm:w-64">
          <span className="sr-only">Dzielnica</span>
          <Icon name="location_city" size={20} className="pointer-events-none absolute left-3.5 text-muted-foreground" />
          <select
            value={search.district ?? ""}
            onChange={(e) => go({ district: e.target.value || undefined })}
            className="h-11 w-full appearance-none border-2 border-input bg-card pr-10 pl-11 text-base font-semibold text-foreground outline-none transition-[border-color,box-shadow] duration-150 hover:border-foreground focus-visible:ring-3 focus-visible:ring-ring"
          >
            <option value="">Cała Warszawa</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <Icon name="expand_more" size={22} className="pointer-events-none absolute right-3 text-muted-foreground" />
        </label>
        <ToggleGroup
          type="multiple"
          variant="pill"
          aria-label="Dodatkowe filtry"
          value={flags}
          onValueChange={(v) => go({ free: v.includes("free"), indoor: v.includes("indoor") })}
          className="-m-1.5 overflow-x-auto p-1.5 [scrollbar-width:none]"
        >
          <ToggleGroupItem value="free">
            <Icon name="money_off" size={18} />
            Tylko darmowe
          </ToggleGroupItem>
          <ToggleGroupItem value="indoor">
            <Icon name="roofing" size={18} />
            Pod dachem
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>
  );
}

function EmptyState({ filtered, when }: { filtered: boolean; when: ExploreSearch["when"] }) {
  return (
    <div className="flex flex-col items-center gap-2.5 border-2 border-dashed border-input px-5 py-8 text-center">
      <Icon name="event_busy" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Nic nie znaleźliśmy dla tych filtrów</p>
      {filtered ? (
        <Button asChild size="sm">
          <Link to="/eksploruj" search={{ ...DEFAULT_EXPLORE, when }}>
            Wyczyść filtry
          </Link>
        </Button>
      ) : (
        when !== "weekend" && (
          <Button asChild size="sm">
            <Link to="/eksploruj" search={{ ...DEFAULT_EXPLORE, when: "weekend" }}>
              Zobacz weekend
            </Link>
          </Button>
        )
      )}
    </div>
  );
}

export function ExploreView() {
  const search = route.useSearch();
  const navigate = route.useNavigate();
  const now = new Date();
  const params = eventsParams(search, now);
  const events = useEvents(params);
  const onboarding = useOnboarding();
  const { position, status } = useLocation();
  const [shown, setShown] = useState(PAGE);

  useEffect(() => startLocation(), []);

  const go = useCallback<Go>(
    (next) => {
      setShown(PAGE);
      void navigate({ search: (prev) => ({ ...prev, ...next }), replace: "q" in next });
    },
    [navigate],
  );

  const data = events.data;
  const cards = data ? sortCards(data.items, position, now) : [];
  const districts = districtOptions(onboarding.data?.steps, data?.items ?? []);
  const filtered = search.q !== "" || search.cat !== "all" || search.district !== undefined || search.free || search.indoor;
  const stale = events.isPlaceholderData;

  return (
    <>
      <PageHeader title="Eksploruj">Wszystko, co dzieje się w Warszawie – bez filtra profilu.</PageHeader>
      <Filters search={search} params={params} districts={districts} go={go} />

      {events.isError && !data ? (
        <RouteError message={errorText(events.error, "Nie udało się pobrać wydarzeń.")} onRetry={() => void events.refetch()} />
      ) : !data ? (
        <GridSkeleton />
      ) : (
        <>
          <div className="flex flex-col gap-1 text-meta text-muted-foreground" aria-live="polite">
            <p>
              <b className="text-foreground">{eventCountLabel(data.total ?? cards.length)}</b>
              {data.total !== undefined && data.total > cards.length && ` (pokazujemy ${cards.length} najbliższych)`}
              {cards.length > 1 && (position ? " · najbliżej Ciebie najpierw" : " · od najbliższego startu")}
              {stale && " · odświeżamy…"}
            </p>
            {status === "denied" && (
              <p className="flex items-center gap-1.5">
                <Icon name="location_off" size={18} />
                Włącz lokalizację w przeglądarce, aby sortować po odległości.
              </p>
            )}
          </div>

          {cards.length > 0 ? (
            <>
              <div className={cn(GRID, "transition-opacity duration-200", stale && "opacity-60")}>
                {cards.slice(0, shown).map((c) => (
                  <EventCard key={c.id} card={c} position={position} now={now} />
                ))}
              </div>
              {cards.length > shown && (
                <Button variant="outline" className="self-center" onClick={() => setShown((n) => n + PAGE)}>
                  Pokaż więcej ({cards.length - shown})
                </Button>
              )}
            </>
          ) : (
            <EmptyState filtered={filtered} when={search.when} />
          )}

          <p className="text-sm text-muted-foreground">
            Wydarzenia z kalendarza miasta, zajęć sportowych i od organizatorów (dane.um.warszawa.pl i partnerzy).
          </p>
        </>
      )}
    </>
  );
}
