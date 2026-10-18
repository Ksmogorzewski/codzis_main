import { getRouteApi, Link } from "@tanstack/react-router";
import { useCallback, useEffect } from "react";
import { errorText, RouteError } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useMe } from "@/hooks/use-me.query";
import { useOnboarding } from "@/hooks/use-onboarding.query";
import { useEventStats } from "@/hooks/use-event-stats.query";
import { useColdStart, useRecommendations } from "@/hooks/use-recommendations.query";
import { isNeedsOnboarding } from "@/lib/api";
import { withStats } from "@/lib/community";
import { filterByCategory } from "@/lib/categories";
import { areaLabel, countLabel, dateTitle, dayLine, posterTitle, readAtLabel, WHEN_OPTIONS } from "@/lib/events";
import { startLocation, useLocation } from "@/lib/location";
import {
  DEFAULT_SEARCH,
  type HomeSearch,
  type HomeWhen,
  type RecommendationsParams,
  recommendationsParams,
  rememberSearch,
} from "@/lib/search";
import { cn } from "@/lib/utils";
import { summary } from "@/lib/wizard";
import { GRID, GridSkeleton } from "./card-skeleton";
import { CategoryFilter } from "./category-filter";
import { EventCard } from "./event-card";
import { NewQuestionsBanner } from "./new-questions-banner";
import { SearchBox } from "./search-box";
import { WhenFilter } from "./when-filter";

const route = getRouteApi("/_app/");

/** Na ekranie do 12 kart (API zwraca do 16, żeby po filtrze kategorii nadal było co pokazać). */
const MAX_CARDS = 12;

const TITLE: Record<Exclude<HomeWhen, "date">, string> = {
  today: "Co robimy dziś?",
  tomorrow: "Co robimy jutro?",
  weekend: "Co robimy w weekend?",
};


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

/** Wielkie słowo nagłówka: „dziś?” prawie na całą szerokość, dłuższe („tym tygodniu?”) mniejsze. */
function bigSize(big: string): string {
  if (big.length <= 6) return "text-[112px] md:text-[200px]";
  if (big.length <= 9) return "text-[88px] md:text-[160px]";
  return "text-[60px] md:text-[112px]";
}

/** Nagłówek-plakat: czerwone pole z datą i wielkim „dziś?”, obok czarne pole z profilem. */
function Hero({ params }: { params: RecommendationsParams }) {
  const profile = useProfileSummary();
  const title = params.when === "date" && params.date ? dateTitle(params.date, new Date()) : TITLE[params.when === "date" ? "today" : params.when];
  const { lead, big } = posterTitle(title);
  return (
    <section className="flex flex-wrap border-2 border-input">
      <div className="min-w-0 flex-[999_1_520px] overflow-hidden bg-poster-kultura px-5 pt-5 pb-3 text-poster-kultura-foreground md:px-7 md:pt-6 md:pb-4">
        <p className="text-[13px] font-bold tracking-[0.12em] uppercase md:text-[15px]">{dayLine(new Date())}</p>
        <h1 className="mt-3 break-words">
          {lead && (
            <span className="block font-display text-[34px] leading-none font-bold tracking-[-0.02em] [font-stretch:115%] md:text-[46px]">
              {lead}
            </span>
          )}
          <span
            // rozmiar przed leading: tailwind-merge usuwa leading-* stojące przed klasą rozmiaru tekstu
            className={cn(
              bigSize(big),
              // mt w em: miejsce na kreskę nad „Ś” przy ciasnej interlinii
              "mt-[0.2em] block font-display leading-[0.82] font-black tracking-[-0.02em] uppercase [font-stretch:55%]",
            )}
          >
            {big}
          </span>
        </h1>
      </div>
      <div className="flex flex-[1_1_300px] flex-col justify-between gap-6 bg-poster-ink px-5 py-5 text-poster-ink-foreground md:px-7 md:py-6">
        <div>
          <p className="text-[13px] font-bold tracking-[0.12em] text-poster-rekreacja uppercase">Dla profilu</p>
          <p className="mt-2 font-display text-[28px] leading-[1.02] font-extrabold text-balance [font-stretch:90%] md:text-[34px]">
            {profile ?? "…"}
          </p>
        </div>
        <Link
          to="/profil"
          className="inline-flex min-h-11 items-center self-start font-bold underline decoration-2 underline-offset-4 outline-none hover:text-poster-rekreacja focus-visible:ring-3 focus-visible:ring-poster-ink-foreground"
        >
          Zmień odpowiedzi
        </Link>
      </div>
    </section>
  );
}

function Filters({ search, go }: { search: HomeSearch; go: (next: Partial<HomeSearch>) => void }) {
  const onQuery = useCallback((q: string) => go({ q }), [go]);
  const params = recommendationsParams(search);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <WhenFilter
          options={WHEN_OPTIONS.filter((o): o is { id: Exclude<HomeWhen, "date">; label: string } => o.id !== "date" && o.id !== "week")}
          value={params.when}
          date={params.date}
          onWhen={(when) => go({ when, date: undefined })}
          onDate={(date) => go({ when: "date", date })}
        />
        <SearchBox value={search.q} onChange={onQuery} />
      </div>
      <CategoryFilter value={search.cat} onChange={(cat) => go({ cat })} />
    </div>
  );
}

function EmptyState({ search }: { search: HomeSearch }) {
  const filtered = search.q !== "" || search.cat !== "all";
  return (
    <div className="flex flex-col items-center gap-2.5 border-2 border-dashed border-input px-5 py-8 text-center">
      <Icon name="event_busy" size={40} className="text-muted-foreground" />
      <p className="text-lg font-bold">Brak propozycji dla tych filtrów</p>
      {filtered && (
        <Button asChild size="sm">
          <Link to="/" search={{ ...DEFAULT_SEARCH, when: search.when }}>
            Wyczyść filtry
          </Link>
        </Button>
      )}
    </div>
  );
}

/** Eksploruj nie ma pozycji w menu: na końcu propozycji (i w pustym stanie) link do wszystkich wydarzeń. */
function AllEventsLink() {
  return (
    <p className="flex justify-center">
      <Link
        to="/eksploruj"
        className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-1 text-base font-bold text-brand-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring"
      >
        Nie pasuje? Zobacz wszystkie wydarzenia
        <Icon name="arrow_forward" size={20} />
      </Link>
    </p>
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
    <div className="flex flex-col items-center gap-2.5 border-2 border-dashed border-input px-5 py-8 text-center">
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
  const params = recommendationsParams(search);
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
  // Karty rekomendacji nie mają zapisów: liczniki i „czy ja” jednym zapytaniem dla całego zestawu.
  const stats = useEventStats(data?.items.map((c) => c.id) ?? []);
  const cards = data ? withStats(filterByCategory(data.items, search.cat).slice(0, MAX_CARDS), stats.data) : [];
  const now = new Date();
  const readAt = readAtLabel(data?.index.builtAt ?? null);
  const stale = recs.isPlaceholderData;

  return (
    <>
      <NewQuestionsBanner />
      <Hero params={params} />
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
              {stale ? " · odświeżamy…" : data.updating && " · dopracowujemy propozycje…"}
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
          <AllEventsLink />

          <p className="text-sm text-muted-foreground">
            Dopasowane do Twojego profilu. Wydarzenia z kalendarza miasta, zajęć sportowych i od organizatorów
            {readAt ? ` · dane z ${readAt}` : ""}.
          </p>
        </>
      )}
    </>
  );
}
