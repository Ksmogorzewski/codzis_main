import { getRouteApi, Link } from "@tanstack/react-router";
import { useCallback, useEffect } from "react";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMe } from "@/hooks/use-me.query";
import { useOnboarding } from "@/hooks/use-onboarding.query";
import { useColdStart, useRecommendations } from "@/hooks/use-recommendations.query";
import { isNeedsOnboarding } from "@/lib/api";
import { CATEGORIES, CATEGORY_LABEL, type Category, filterByCategory } from "@/lib/categories";
import { areaLabel, countLabel, dayLine, readAtLabel, WHEN_OPTIONS } from "@/lib/events";
import { startLocation, useLocation } from "@/lib/location";
import { WHEN_VALUES, type When } from "@/lib/schemas";
import { DEFAULT_SEARCH, type HomeSearch, rememberSearch } from "@/lib/search";
import { cn } from "@/lib/utils";
import { summary } from "@/lib/wizard";
import { GRID, GridSkeleton } from "./card-skeleton";
import { EventCard } from "./event-card";
import { SearchBox } from "./search-box";

const route = getRouteApi("/_app/");

/** Na ekranie do 12 kart (API zwraca do 16, żeby po filtrze kategorii nadal było co pokazać). */
const MAX_CARDS = 12;

const TITLE: Record<When, string> = {
  today: "Co robimy dziś?",
  tomorrow: "Co robimy jutro?",
  weekend: "Co robimy w weekend?",
  week: "Co robimy w tym tygodniu?",
};

const isWhen = (v: string): v is When => (WHEN_VALUES as readonly string[]).includes(v);
const isCategory = (v: string): v is Category => (CATEGORIES as readonly string[]).includes(v);

/** "Rodzina z dziećmi · Chill" z kroków „z kim” i „klimat” (jak w ich Home.tsx). */
function useProfileSummary(): string | null {
  const me = useMe();
  const onboarding = useOnboarding();
  if (!me.data || !onboarding.data) return null;
  const answers = me.data.profile?.answers ?? {};
  const labels = onboarding.data.steps
    .filter((s) => s.id === "who" || s.id === "vibe")
    .flatMap((s) => summary(s, answers))
    .slice(0, 3);
  return labels.join(" · ") || "jeszcze nieuzupełniony";
}

function Hero({ when }: { when: When }) {
  const profile = useProfileSummary();
  return (
    <section className="flex flex-col gap-1.5 rounded-3xl bg-primary p-6 text-primary-foreground">
      <p className="text-meta font-semibold opacity-85">{dayLine(new Date())}</p>
      <h1 className="text-[32px] leading-[1.05] font-extrabold tracking-[-0.03em] text-balance md:text-[40px]">
        {TITLE[when]}
      </h1>
      <p className="mt-1 text-lg opacity-90">
        Propozycje dla profilu: {profile ?? "…"}{" "}
        <Link
          to="/profil"
          className="inline-flex min-h-11 items-center rounded-sm font-bold underline underline-offset-2 outline-none focus-visible:ring-3 focus-visible:ring-primary-foreground"
        >
          edytuj
        </Link>
      </p>
    </section>
  );
}

function Filters({ search, go }: { search: HomeSearch; go: (next: Partial<HomeSearch>) => void }) {
  const onQuery = useCallback((q: string) => go({ q }), [go]);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <ToggleGroup
          type="single"
          variant="segment"
          aria-label="Kiedy"
          value={search.when}
          onValueChange={(v) => isWhen(v) && go({ when: v })}
          className="max-w-full overflow-x-auto [scrollbar-width:none]"
        >
          {WHEN_OPTIONS.map((o) => (
            <ToggleGroupItem key={o.id} value={o.id}>
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <SearchBox value={search.q} onChange={onQuery} />
      </div>
      <ToggleGroup
        type="single"
        variant="pill"
        aria-label="Kategoria"
        value={search.cat}
        onValueChange={(v) => isCategory(v) && go({ cat: v })}
        className="-m-1.5 overflow-x-auto p-1.5 [scrollbar-width:none]"
      >
        {CATEGORIES.map((id) => (
          <ToggleGroupItem key={id} value={id}>
            {CATEGORY_LABEL[id]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

function EmptyState({ search }: { search: HomeSearch }) {
  const filtered = search.q !== "" || search.cat !== "all";
  return (
    <div className="flex flex-col items-center gap-2.5 rounded-2xl border-[1.5px] border-dashed border-input px-5 py-8 text-center">
      <Icon name="event_busy" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Brak propozycji dla tych filtrów</p>
      {filtered ? (
        <Button asChild size="sm">
          <Link to="/" search={{ ...DEFAULT_SEARCH, when: search.when }}>
            Wyczyść filtry
          </Link>
        </Button>
      ) : (
        search.when !== "week" && (
          <Button asChild size="sm">
            <Link to="/" search={{ ...DEFAULT_SEARCH, when: "week" }}>
              Pokaż 7 dni
            </Link>
          </Button>
        )
      )}
    </div>
  );
}

function Loading({ coldStart }: { coldStart: boolean }) {
  return (
    <>
      <p role="status" className="flex items-center gap-2 text-meta text-muted-foreground">
        <Icon name="progress_activity" size={18} className="motion-safe:animate-spin" />
        {coldStart
          ? "Dobieramy propozycje… Za pierwszym razem może to potrwać do pół minuty."
          : "Dobieramy propozycje…"}
      </p>
      <GridSkeleton />
    </>
  );
}

function NeedsProfile({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-2.5 rounded-2xl border-[1.5px] border-dashed border-input px-5 py-8 text-center">
      <Icon name="tune" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">{message}</p>
      <Button asChild size="sm">
        <Link to="/profil">Uzupełnij profil</Link>
      </Button>
    </div>
  );
}

export function HomeView() {
  const search = route.useSearch();
  const navigate = route.useNavigate();
  const params = { when: search.when, q: search.q };
  const recs = useRecommendations(params);
  const coldStart = useColdStart(params);
  const { position, status } = useLocation();

  useEffect(() => startLocation(), []);
  // Filtry wracają po powrocie ze szczegółów i po zapisie profilu.
  useEffect(() => rememberSearch(search), [search]);

  const go = useCallback(
    (next: Partial<HomeSearch>) => navigate({ search: (prev) => ({ ...prev, ...next }), replace: "q" in next }),
    [navigate],
  );

  const data = recs.data;
  const cards = data ? filterByCategory(data.items, search.cat).slice(0, MAX_CARDS) : [];
  const now = new Date();
  const readAt = readAtLabel(data?.index.builtAt ?? null);
  const stale = recs.isPlaceholderData;

  return (
    <>
      <Hero when={search.when} />
      <Filters search={search} go={go} />

      {recs.isError && !data ? (
        isNeedsOnboarding(recs.error) ? (
          <NeedsProfile message={errorText(recs.error)} />
        ) : (
          <RouteError
            message={errorText(recs.error, "Nie udało się pobrać propozycji.")}
            onRetry={() => void recs.refetch()}
          />
        )
      ) : !data ? (
        <Loading coldStart={coldStart} />
      ) : (
        <>
          <div className="flex flex-col gap-1 text-meta text-muted-foreground" aria-live="polite">
            <p>
              <b className="text-foreground">{countLabel(cards.length)}</b> {areaLabel(data)}
              {data.query && <> dla „{data.query}”</>}
              {stale && " · odświeżamy…"}
            </p>
            {data.areaRelaxed && <p>W Twojej okolicy było mało propozycji, więc poszerzyliśmy obszar.</p>}
            {status === "denied" && (
              <p className="flex items-center gap-1.5">
                <Icon name="location_off" size={18} />
                Włącz lokalizację w przeglądarce, aby zobaczyć odległość.
              </p>
            )}
          </div>

          {cards.length > 0 ? (
            <div className={cn(GRID, "transition-opacity duration-200", stale && "opacity-60")}>
              {cards.map((c) => (
                <EventCard key={c.id} card={c} position={position} now={now} />
              ))}
            </div>
          ) : (
            <EmptyState search={search} />
          )}

          <p className="text-sm text-muted-foreground">
            Dopasowane do Twojego profilu. Wydarzenia z kalendarza miasta, zajęć sportowych i od organizatorów
            {readAt ? ` · dane z ${readAt}` : ""}.
          </p>
        </>
      )}
    </>
  );
}
