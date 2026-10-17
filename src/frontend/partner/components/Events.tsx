import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../../shared/Icon";
import { formatDateTime, plural } from "../../shared/format";
import { api } from "../lib/api";
import { STATUS, priceLabel, tagList } from "../lib/labels";
import type { Submission } from "../lib/types";

type Props = { credits: number; onError: (e: unknown) => void; onCount: (n: number) => void };
type Tab = "all" | Submission["status"];

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "Wszystkie" },
  { id: "published", label: "Opublikowane" },
  { id: "queued", label: "W kolejce" },
];

export function Events({ credits, onError, onCount }: Props) {
  const [items, setItems] = useState<Submission[] | null>(null);
  const [tab, setTab] = useState<Tab>("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const latest = useRef<Submission[] | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<{ items: Submission[] }>("GET", "/events")
        .then(({ items }) => {
          if (!alive) return;
          latest.current = items;
          setItems(items);
          onCount(items.length);
        })
        .catch(onError);
    void load();
    // Ogłoszenia "w kolejce" zmieniają status po otagowaniu (~2 min) - odświeżamy, dopóki jakieś czekają
    const timer = window.setInterval(() => {
      if (latest.current?.some((i) => i.status === "queued")) void load();
    }, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [onError, onCount]);

  const counts = useMemo(
    () => ({
      all: items?.length ?? 0,
      published: items?.filter((i) => i.status === "published").length ?? 0,
      queued: items?.filter((i) => i.status === "queued").length ?? 0,
    }),
    [items],
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter(
      (i) => (tab === "all" || i.status === tab) && (!q || `${i.title} ${i.venue?.name ?? ""} ${i.district ?? ""}`.toLowerCase().includes(q)),
    );
  }, [items, tab, query]);

  return (
    <div className="content">
      <div className="content-head">
        <div>
          <h1>Moje wydarzenia</h1>
          <span>
            {items === null
              ? "Ładowanie…"
              : `${plural(counts.all, "wydarzenie", "wydarzenia", "wydarzeń")}${counts.queued ? ` · ${counts.queued} w kolejce do tagowania` : ""}`}
          </span>
        </div>
        <a className="btn" href="#/dodaj">
          <Icon name="add" />
          Dodaj wydarzenie
        </a>
      </div>

      <div className="kpis">
        <div><span className="label">Wszystkie</span><span className="value">{counts.all}</span></div>
        <div><span className="label">Opublikowane</span><span className="value">{counts.published}</span></div>
        <div><span className="label">W kolejce</span><span className="value">{counts.queued}</span></div>
        <div><span className="label">Kredyty</span><span className="value">{credits}</span></div>
      </div>

      <div className="panel">
        <div className="panel-bar">
          <div className="tabs">
            {TABS.map((t) => (
              <button key={t.id} type="button" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}>
                {t.label}
                <span className="count">{counts[t.id]}</span>
              </button>
            ))}
          </div>
          <label className="search">
            <Icon name="search" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Szukaj wydarzenia" aria-label="Szukaj wydarzenia" />
          </label>
        </div>

        <div className="table-head">
          <span>Wydarzenie</span>
          <span className="hide-sm">Termin</span>
          <span>Status</span>
          <span className="hide-sm">Tagi AI</span>
          <span className="hide-sm" />
        </div>

        {rows.map((ev) => {
          const tags = tagList(ev.tags);
          const expanded = open === ev.id;
          return (
            <div key={ev.id}>
              <button type="button" className="table-row" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : ev.id)}>
                <span className="ev-cell">
                  {ev.imageUrl ? (
                    <img className="thumb" src={ev.imageUrl} alt="" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
                  ) : (
                    <span className="thumb thumb-empty"><Icon name="image" /></span>
                  )}
                  <span className="text">
                    <b>{ev.title}</b>
                    <small>
                      {[ev.category?.[0]?.name, ev.declared?.setting, priceLabel(ev)].filter(Boolean).join(" · ")}
                    </small>
                  </span>
                </span>
                <span className="date-cell hide-sm">{formatDateTime(ev.occurrences?.[0]?.start ?? ev.startsAt)}</span>
                <span>
                  <span className={`pill ${STATUS[ev.status].tone}`}>{STATUS[ev.status].label}</span>
                </span>
                <span className="tags-cell hide-sm">
                  {tags.slice(0, 3).map((t) => (
                    <span className="tag" key={t}>{t}</span>
                  ))}
                  {tags.length > 3 && <span className="tag">+{tags.length - 3}</span>}
                  {!tags.length && <span className="muted">{ev.status === "queued" ? "po otagowaniu" : "—"}</span>}
                </span>
                <span className="hide-sm" style={{ justifyContent: "flex-end", color: "var(--muted2)" }}>
                  <Icon name={expanded ? "expand_less" : "expand_more"} />
                </span>
              </button>
              {expanded && (
                <div className="row-details">
                  {ev.lead && <span>{ev.lead}</span>}
                  <dl>
                    <dt>Miejsce</dt>
                    <dd>{[ev.venue?.name, ev.venue?.address, ev.district].filter(Boolean).join(", ") || "—"}</dd>
                    <dt>Termin</dt>
                    <dd>
                      {formatDateTime(ev.occurrences?.[0]?.start)}
                      {ev.occurrences?.[0]?.end ? ` – ${formatDateTime(ev.occurrences[0].end)}` : ""}
                    </dd>
                    <dt>Wstęp</dt>
                    <dd>{[priceLabel(ev), ev.declared?.registration].filter(Boolean).join(" · ")}</dd>
                    {ev.declared?.audience?.length ? (<><dt>Dla kogo</dt><dd>{ev.declared.audience.join(", ")}</dd></>) : null}
                    {ev.attributes?.ticketUrl ? (<><dt>Bilety</dt><dd><a href={ev.attributes.ticketUrl} target="_blank" rel="noopener">{ev.attributes.ticketUrl}</a></dd></>) : null}
                    {ev.url ? (<><dt>Strona</dt><dd><a href={ev.url} target="_blank" rel="noopener">{ev.url}</a></dd></>) : null}
                    <dt>Tagi AI</dt>
                    <dd className="tags-cell">
                      {tags.length ? tags.map((t) => <span className="tag" key={t}>{t}</span>) : "Pojawią się po otagowaniu (zwykle ~2 min)."}
                    </dd>
                    <dt>Dodano</dt>
                    <dd>{formatDateTime(ev.createdAt)}</dd>
                  </dl>
                </div>
              )}
            </div>
          );
        })}

        {items !== null && rows.length === 0 && (
          <div className="empty">
            {items.length === 0 ? (
              <>
                <span>Nie masz jeszcze żadnych wydarzeń.</span>
                <a className="btn" href="#/dodaj"><Icon name="add" />Dodaj pierwsze wydarzenie</a>
              </>
            ) : (
              "Brak wydarzeń dla tego filtra"
            )}
          </div>
        )}
        {items === null && <div className="empty"><span className="spinner" aria-hidden="true" /></div>}
      </div>
    </div>
  );
}
