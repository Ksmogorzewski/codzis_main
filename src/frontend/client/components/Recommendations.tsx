import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "../../shared/Icon";
import { ApiError, api } from "../lib/api";
import { WHEN_OPTIONS, areaLabel, countLabel } from "../lib/events";
import type { Recommendations as Result, When } from "../lib/types";
import { EventCard } from "./EventCard";

type State =
  | { kind: "loading"; slow: boolean }
  | { kind: "error"; message: string; status: number }
  | { kind: "ready"; data: Result };

// Zimny start Lambdy z modelem trwa do ~30 s i HTTP API odpowiada wtedy 503. Ponawiamy z przerwą, żeby
// trafić w rozgrzany już kontener, a nie uruchamiać kolejnego.
const RETRY_STATUSES = [0, 502, 503, 504];
const RETRY_DELAYS = [5000, 10000];

export function Recommendations() {
  const [when, setWhen] = useState<When>("today");
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [state, setState] = useState<State>({ kind: "loading", slow: false });
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(0);

  const load = useCallback(async (w: When, q: string) => {
    const id = ++latest.current;
    setState({ kind: "loading", slow: false });
    const slowTimer = setTimeout(() => id === latest.current && setState({ kind: "loading", slow: true }), 6000);
    const params = new URLSearchParams({ when: w });
    if (q) params.set("q", q);
    try {
      let data: Result | undefined;
      for (let retry = 0; !data; retry++) {
        try {
          data = await api<Result>("GET", `/api/recommendations?${params}`);
        } catch (e) {
          const delay = RETRY_DELAYS[retry];
          if (!(e instanceof ApiError) || !RETRY_STATUSES.includes(e.status) || delay === undefined || id !== latest.current) throw e;
          setState({ kind: "loading", slow: true });
          await new Promise((r) => setTimeout(r, delay));
        }
      }
      if (id === latest.current) setState({ kind: "ready", data });
    } catch (e) {
      if (id !== latest.current) return;
      const status = e instanceof ApiError ? e.status : 0;
      setState({ kind: "error", status, message: e instanceof Error ? e.message : "Nie udało się pobrać propozycji." });
    } finally {
      clearTimeout(slowTimer);
    }
  }, []);

  useEffect(() => {
    load(when, query);
  }, [load, when, query, attempt]);

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
            <button key={o.id} type="button" aria-pressed={when === o.id} onClick={() => setWhen(o.id)}>
              {o.label}
            </button>
          ))}
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

      {state.kind === "loading" && (
        <>
          <p className="rec-info" role="status">
            <span className="spinner spinner-sm" aria-hidden="true" />
            {state.slow ? "Uruchamiamy dopasowanie – pierwszy raz może to potrwać do pół minuty…" : "Dobieramy propozycje…"}
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

      {state.kind === "error" && (
        <div className="empty">
          <Icon name={state.status === 409 ? "tune" : "cloud_off"} size={40} />
          <div className="empty-title">{state.message}</div>
          {state.status === 409 ? (
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

      {state.kind === "ready" && (
        <>
          <p className="rec-info">
            <span>
              <b>{countLabel(state.data.items.length)}</b> {areaLabel(state.data)}
              {state.data.query && <> dla „{state.data.query}”</>}
            </span>
            {state.data.query && (
              <button className="chip-clear" type="button" onClick={clearSearch}>
                <Icon name="close" />
                Wyczyść
              </button>
            )}
          </p>
          {state.data.areaRelaxed && (
            <p className="rec-note">
              <Icon name="travel_explore" />W Twojej okolicy było mało propozycji, więc poszerzyliśmy obszar.
            </p>
          )}
          {state.data.items.length > 0 ? (
            <div className="ev-grid">
              {state.data.items.map((item) => (
                <EventCard key={item.id} item={item} now={new Date(state.data.generatedAt)} />
              ))}
            </div>
          ) : (
            <div className="empty">
              <Icon name="event_busy" size={40} />
              <div className="empty-title">Brak propozycji dla tych filtrów</div>
              {state.data.query ? (
                <button className="btn" type="button" onClick={clearSearch}>
                  Wyczyść wyszukiwanie
                </button>
              ) : (
                when !== "week" && (
                  <button className="btn" type="button" onClick={() => setWhen("week")}>
                    Pokaż cały tydzień
                  </button>
                )
              )}
            </div>
          )}
          <p className="rec-foot">
            {state.data.ranking === "llm"
              ? "Kolejność i uzasadnienia ułożyła AI na podstawie Twojego profilu."
              : "Dopasowane do Twojego profilu."}{" "}
            Wydarzenia z kalendarza miasta, zajęć sportowych i od organizatorów.
          </p>
        </>
      )}
    </section>
  );
}
