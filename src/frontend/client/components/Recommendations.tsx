import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "../../shared/Icon";
import { ApiError, api } from "../lib/api";
import { WHEN_OPTIONS, areaLabel, chosenDayLabel, countLabel, dateBounds, preparedLabel } from "../lib/events";
import type { Preparing, Recommendations as Result, When } from "../lib/types";
import { EventCard } from "./EventCard";

type Choice = { when: When; date?: string };
type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "error"; message: string; status: number }
  | { kind: "ready"; data: Result };

// Zestawy, które serwer liczy z góry (w nocy, po zmianie profilu) - dociągamy je w tle
const DEFAULT_SETS: When[] = ["today", "tomorrow", "weekend"];
// Zimny start Lambdy z modelem trwa do ~30 s i HTTP API odpowiada wtedy 503. Ponawiamy z przerwą, żeby
// trafić w rozgrzany już kontener, a nie uruchamiać kolejnego.
const RETRY_STATUSES = [0, 502, 503, 504];
const RETRY_DELAYS = [5000, 10000];
const PREPARING_LIMIT_MS = 150_000; // zestaw liczony po zmianie profilu: czekamy najwyżej tyle

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function setParams(choice: Choice, query: string): string {
  const params = new URLSearchParams({ when: choice.when });
  if (choice.date) params.set("date", choice.date);
  if (query) params.set("q", query);
  return params.toString();
}

// Jeden zestaw: 202 "preparing" (liczy się po zmianie profilu) -> pytamy ponownie, 5xx -> ponawiamy
async function request(params: string): Promise<Result> {
  const started = Date.now();
  let retry = 0;
  for (;;) {
    let data: Result | Preparing;
    try {
      data = await api<Result | Preparing>("GET", `/api/recommendations?${params}`);
    } catch (e) {
      const delay = RETRY_DELAYS[retry++];
      if (!(e instanceof ApiError) || !RETRY_STATUSES.includes(e.status) || delay === undefined) throw e;
      await sleep(delay);
      continue;
    }
    if (!("status" in data)) return data;
    if (Date.now() - started > PREPARING_LIMIT_MS) {
      throw new ApiError(503, "Przygotowanie propozycji trwa dłużej niż zwykle – spróbuj ponownie.");
    }
    await sleep((data.retryAfter || 2) * 1000);
  }
}

export function Recommendations() {
  const [choice, setChoice] = useState<Choice>({ when: "today" });
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(0);
  const dateInput = useRef<HTMLInputElement>(null);
  // Zestawy z tej wizyty: przełączanie dni bez kolejnych zapytań (zapisane są też na serwerze)
  const sets = useRef(new Map<string, Result>());
  const inFlight = useRef(new Map<string, Promise<Result>>());

  const fetchSet = useCallback((c: Choice, q: string): Promise<Result> => {
    const key = setParams(c, q);
    const ready = sets.current.get(key);
    if (ready) return Promise.resolve(ready);
    let running = inFlight.current.get(key);
    if (!running) {
      running = request(key)
        .then((data) => {
          sets.current.set(key, data);
          return data;
        })
        .finally(() => inFlight.current.delete(key));
      inFlight.current.set(key, running);
    }
    return running;
  }, []);

  // Po pierwszym zestawie po cichu, po kolei, dociągamy pozostałe: dziś / jutro / weekend
  const prefetch = useCallback(async () => {
    for (const when of DEFAULT_SETS) await fetchSet({ when }, "").catch(() => undefined);
  }, [fetchSet]);

  useEffect(() => {
    const id = ++latest.current;
    if (sets.current.has(setParams(choice, query))) return; // pokazany od razu z pamięci (niżej)
    setState({ kind: "loading", slow: false });
    const slowTimer = setTimeout(() => id === latest.current && setState({ kind: "loading", slow: true }), 6000);
    fetchSet(choice, query)
      .then((data) => {
        if (id === latest.current) setState({ kind: "ready", data });
        if (!query) void prefetch();
      })
      .catch((e) => {
        if (id !== latest.current) return;
        const status = e instanceof ApiError ? e.status : 0;
        setState({ kind: "error", status, message: e instanceof Error ? e.message : "Nie udało się pobrać propozycji." });
      })
      .finally(() => clearTimeout(slowTimer));
    return () => clearTimeout(slowTimer);
  }, [choice, query, attempt, fetchSet, prefetch]);

  // Zestaw już pobrany w tej wizycie: od razu, bez klatki z poprzednią listą
  const remembered = sets.current.get(setParams(choice, query));
  const view: State = remembered ? { kind: "ready", data: remembered } : state;
  const now = new Date();
  const bounds = dateBounds(now);
  const openPicker = () => {
    const el = dateInput.current;
    if (!el) return;
    try {
      el.showPicker();
    } catch {
      el.focus();
      el.click();
    }
  };
  const search = (e: FormEvent) => {
    e.preventDefault();
    setQuery(input.trim());
  };
  const clearSearch = () => {
    setInput("");
    setQuery("");
  };

  return (
    <section className="recs" aria-labelledby="recs-title">
      <h2 id="recs-title" className="visually-hidden">
        Rekomendacje
      </h2>
      <div className="rec-controls">
        <div className="seg" role="group" aria-label="Kiedy">
          {WHEN_OPTIONS.map((o) => (
            <button key={o.id} type="button" aria-pressed={choice.when === o.id} onClick={() => setChoice({ when: o.id })}>
              {o.label}
            </button>
          ))}
          <button type="button" aria-pressed={choice.when === "date"} onClick={openPicker}>
            <Icon name="calendar_month" />
            {choice.when === "date" && choice.date ? chosenDayLabel(choice.date, now) : "Inny dzień"}
          </button>
          <input
            ref={dateInput}
            className="seg-date"
            type="date"
            min={bounds.min}
            max={bounds.max}
            value={choice.when === "date" ? choice.date : ""}
            onChange={(e) => e.target.value && setChoice({ when: "date", date: e.target.value })}
            tabIndex={-1}
            aria-label="Wybierz dzień"
          />
        </div>
        <form className="rec-search" role="search" onSubmit={search}>
          <Icon name="search" />
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Np. jazz, joga, ceramika"
            aria-label="Szukaj wydarzeń"
            maxLength={120}
          />
          <button className="btn btn-sm" type="submit">
            Szukaj
          </button>
        </form>
      </div>

      {view.kind === "loading" && (
        <>
          <p className="rec-info" role="status">
            <span className="spinner spinner-sm" aria-hidden="true" />
            {view.slow ? "Przygotowujemy propozycje dopasowane do Twojego profilu – to może chwilę potrwać…" : "Dobieramy propozycje…"}
          </p>
          <div className="ev-grid" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div className="ev-card ev-skeleton" key={i}>
                <div className="ev-img" />
                <div className="ev-body">
                  <span className="sk sk-title" />
                  <span className="sk" />
                  <span className="sk sk-short" />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {view.kind === "error" && (
        <div className="empty">
          <Icon name={view.status === 409 ? "tune" : "cloud_off"} size={40} />
          <div className="empty-title">{view.message}</div>
          {view.status === 409 ? (
            <a className="btn" href="#/profil">
              Uzupełnij profil
            </a>
          ) : (
            <button className="btn" type="button" onClick={() => setAttempt((n) => n + 1)}>
              Spróbuj ponownie
            </button>
          )}
        </div>
      )}

      {view.kind === "ready" && (
        <>
          <p className="rec-info">
            <span>
              <b>{countLabel(view.data.items.length)}</b> {areaLabel(view.data)}
              {view.data.query && <> dla „{view.data.query}”</>}
            </span>
            {view.data.query && (
              <button className="chip-clear" type="button" onClick={clearSearch}>
                <Icon name="close" />
                Wyczyść
              </button>
            )}
          </p>
          {view.data.areaRelaxed && (
            <p className="rec-note">
              <Icon name="travel_explore" />W Twojej okolicy było mało propozycji, więc poszerzyliśmy obszar.
            </p>
          )}
          {view.data.items.length > 0 ? (
            <div className="ev-grid">
              {view.data.items.map((item) => (
                <EventCard key={item.id} item={item} now={now} />
              ))}
            </div>
          ) : (
            <div className="empty">
              <Icon name="event_busy" size={40} />
              <div className="empty-title">Brak propozycji dla tych filtrów</div>
              {view.data.query ? (
                <button className="btn" type="button" onClick={clearSearch}>
                  Wyczyść wyszukiwanie
                </button>
              ) : choice.when !== "weekend" ? (
                <button className="btn" type="button" onClick={() => setChoice({ when: "weekend" })}>
                  Pokaż weekend
                </button>
              ) : (
                <button className="btn" type="button" onClick={openPicker}>
                  Wybierz inny dzień
                </button>
              )}
            </div>
          )}
          <p className="rec-foot">
            {preparedLabel(view.data.generatedAt, now)} ·{" "}
            {view.data.ranking === "llm"
              ? "kolejność i uzasadnienia ułożyła AI na podstawie Twojego profilu."
              : "dopasowane do Twojego profilu."}{" "}
            Wydarzenia z kalendarza miasta, zajęć sportowych i od organizatorów.
          </p>
        </>
      )}
    </section>
  );
}
