import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "../../shared/Icon";
import { creditsLabel, formatMoney, withTimezone } from "../../shared/format";
import { useToast } from "../../shared/toast";
import { ApiError, FIELD_LABELS, api } from "../lib/api";
import { config } from "../lib/config";
import { SETTING_ICONS } from "../lib/labels";
import type { CreatedEvent, Profile } from "../lib/types";
import { EventPreview } from "./EventPreview";

type Props = { profile: Profile; onError: (e: unknown) => void; onPublished: () => Promise<void> };

type Form = {
  title: string;
  lead: string;
  text: string;
  category: string;
  url: string;
  startsAt: string;
  endsAt: string;
  venue: string;
  street: string;
  streetNumber: string;
  district: string;
  setting: string;
  cost: string;
  priceMin: string;
  priceMax: string;
  registration: string;
  ticketUrl: string;
  audience: string[];
  accessibility: string[];
};

const EMPTY: Form = {
  title: "", lead: "", text: "", category: "", url: "", startsAt: "", endsAt: "", venue: "", street: "", streetNumber: "",
  district: "", setting: "", cost: "", priceMin: "", priceMax: "", registration: "", ticketUrl: "", audience: [], accessibility: [],
};
const REQUIRED: (keyof Form)[] = ["title", "lead", "category", "startsAt", "venue", "district", "setting", "cost", "registration"];
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function EventForm({ profile, onError, onPublished }: Props) {
  const toast = useToast();
  const cfg = config();
  const options = profile.formOptions;
  const [form, setForm] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Set<string>>(new Set());
  const [photo, setPhoto] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const photoUrl = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => () => void (photoUrl && URL.revokeObjectURL(photoUrl)), [photoUrl]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      if (!e.has(key)) return e;
      const next = new Set(e);
      next.delete(key);
      return next;
    });
  };
  const toggle = (key: "audience" | "accessibility", value: string) =>
    set(key, form[key].includes(value) ? form[key].filter((v) => v !== value) : [...form[key], value]);

  function choosePhoto(file: File | undefined) {
    if (!file) return;
    if (!PHOTO_TYPES.includes(file.type)) {
      toast("Zdjęcie musi być w formacie JPG, PNG lub WebP", "error");
      return;
    }
    if (file.size > cfg.maxPhotoMb * 1024 * 1024) {
      toast(`Zdjęcie jest za duże (max ${cfg.maxPhotoMb} MB)`, "error");
      return;
    }
    setPhoto(file);
    setErrors((e) => new Set([...e].filter((x) => x !== "photo")));
  }

  const paid = form.cost === "Płatne";
  const walkIn = form.registration === "Wstęp wolny";
  const enoughCredits = profile.credits >= profile.eventCost;
  const priceText = !form.cost
    ? "Cena"
    : !paid
      ? "Bezpłatne"
      : form.priceMin
        ? `od ${formatMoney(Number(form.priceMin), cfg.currency)}`
        : "Płatne";

  function validate(): string[] {
    const missing: string[] = REQUIRED.filter((k) => !String(form[k]).trim());
    if (!photo) missing.push("photo");
    if (form.endsAt && form.startsAt && form.endsAt < form.startsAt) missing.push("endsAt");
    if (paid && form.priceMin && form.priceMax && Number(form.priceMax) < Number(form.priceMin)) missing.push("priceMax");
    for (const k of ["url", "ticketUrl"] as const) if (form[k] && !/^https?:\/\//.test(form[k])) missing.push(k);
    return missing;
  }

  async function publish() {
    const problems = validate();
    if (problems.length) {
      setErrors(new Set(problems));
      toast(`Uzupełnij: ${problems.map((p) => (p === "photo" ? "zdjęcie" : FIELD_LABELS[p] ?? p)).join(", ")}`, "error");
      return;
    }
    if (!enoughCredits) {
      toast("Brak kredytów – doładuj je w zakładce Płatności", "error");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...form,
        startsAt: withTimezone(form.startsAt),
        endsAt: form.endsAt ? withTimezone(form.endsAt) : undefined,
        priceMin: paid && form.priceMin ? form.priceMin : undefined,
        priceMax: paid && form.priceMax ? form.priceMax : undefined,
        ticketUrl: walkIn ? undefined : form.ticketUrl || undefined,
        photoContentType: photo!.type,
      };
      const created = await api<CreatedEvent>("POST", "/events", payload);

      // Presigned POST: pola z odpowiedzi muszą być przed plikiem
      const upload = new FormData();
      Object.entries(created.upload.fields).forEach(([k, v]) => upload.append(k, v));
      upload.append("file", photo!);
      const res = await fetch(created.upload.url, { method: "POST", body: upload }).catch(() => null);

      if (res?.ok) toast("Wydarzenie przyjęte – pojawi się w aplikacji po otagowaniu (zwykle ~2 min).");
      else toast(`Wydarzenie zapisane, ale nie udało się wysłać zdjęcia${res ? ` (HTTP ${res.status})` : ""}.`, "error");
      setForm(EMPTY);
      setPhoto(null);
      await onPublished();
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) setErrors(new Set(e.fields));
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  const field = (name: keyof Form | "photo", label: string, control: ReactNode, opts: { wide?: boolean; hint?: string } = {}) => (
    <label className={`field${opts.wide ? " span-all" : ""}${errors.has(name) ? " invalid" : ""}`}>
      <span>
        {label}
        {REQUIRED.includes(name as keyof Form) && <span className="req"> *</span>}
      </span>
      {control}
      {opts.hint && <span className="field-hint">{opts.hint}</span>}
    </label>
  );
  const input = (name: keyof Form, props: Record<string, unknown> = {}) => (
    <input value={form[name] as string} onChange={(e) => set(name, e.target.value as never)} {...props} />
  );
  const group = (name: keyof Form, label: string, control: ReactNode, wide = false) => (
    <div className={`field${wide ? " span-all" : ""}${errors.has(name) ? " invalid" : ""}`}>
      <span>
        {label}
        {REQUIRED.includes(name) && <span className="req"> *</span>}
      </span>
      {control}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div className="edit-bar">
        <a className="icon-btn" href="#/wydarzenia" aria-label="Wróć do listy">
          <Icon name="arrow_back" size={18} />
        </a>
        <div className="crumb">
          <small>Moje wydarzenia /</small>
          <b>{form.title || "Nowe wydarzenie"}</b>
        </div>
        <span className="pill draft">Szkic</span>
        {enoughCredits ? (
          <button className="btn" type="button" onClick={publish} disabled={busy}>
            {busy ? "Publikowanie…" : `Opublikuj · ${creditsLabel(profile.eventCost)}`}
          </button>
        ) : (
          <a className="btn" href="#/platnosci">
            <Icon name="payments" />
            Doładuj kredyty
          </a>
        )}
      </div>

      <div className="edit-grid">
        <div className="edit-main">
          <section className="section">
            <h2>Podstawowe informacje</h2>
            {field("title", "Nazwa wydarzenia", input("title", { maxLength: 200 }), { wide: true })}
            {field("lead", "Krótki opis", <textarea rows={2} maxLength={500} value={form.lead} onChange={(e) => set("lead", e.target.value)} />, {
              wide: true,
              hint: "1–2 zdania widoczne na liście rekomendacji",
            })}
            {field("text", "Pełny opis", <textarea rows={5} maxLength={5000} value={form.text} onChange={(e) => set("text", e.target.value)} />, {
              wide: true,
              hint: "Pusta linia rozdziela akapity",
            })}
            {group(
              "category",
              "Kategoria",
              <div className="checks">
                {cfg.categories.map((c) => (
                  <button key={c} type="button" className="check" aria-pressed={form.category === c} onClick={() => set("category", c)}>
                    {c}
                  </button>
                ))}
              </div>,
              true,
            )}
            {field("url", "Link do strony wydarzenia", input("url", { type: "url", placeholder: "https://", maxLength: 500 }), { wide: true })}
          </section>

          <section className="section">
            <h2>Termin i miejsce</h2>
            {field("startsAt", "Początek", input("startsAt", { type: "datetime-local" }))}
            {field("endsAt", "Koniec", input("endsAt", { type: "datetime-local" }))}
            {field("venue", "Nazwa miejsca", input("venue", { maxLength: 200, placeholder: "np. OCH-Teatr" }), { wide: true })}
            {field("street", "Ulica", input("street", { maxLength: 200, placeholder: "ul. Grójecka" }))}
            {field("streetNumber", "Numer", input("streetNumber", { maxLength: 20 }))}
            {field(
              "district",
              "Dzielnica",
              <select value={form.district} onChange={(e) => set("district", e.target.value)}>
                <option value="">— wybierz —</option>
                {cfg.districts.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>,
            )}
            {group(
              "setting",
              "Gdzie się odbywa",
              <div className="segmented">
                {options.setting.map((o) => (
                  <button key={o} type="button" aria-pressed={form.setting === o} onClick={() => set("setting", o)} title={o}>
                    <Icon name={SETTING_ICONS[o] ?? "location_on"} />
                    {o === "W pomieszczeniu i na zewnątrz" ? "Oba" : o === "W pomieszczeniu" ? "Pod dachem" : "Plener"}
                  </button>
                ))}
              </div>,
            )}
          </section>

          <section className="section">
            <h2>Wstęp i bilety</h2>
            {group(
              "cost",
              "Wstęp",
              <div className="segmented">
                {options.cost.map((o) => (
                  <button key={o} type="button" aria-pressed={form.cost === o} onClick={() => set("cost", o)}>
                    {o}
                  </button>
                ))}
              </div>,
            )}
            {field(
              "registration",
              "Zapisy i bilety",
              <select value={form.registration} onChange={(e) => set("registration", e.target.value)}>
                <option value="">— wybierz —</option>
                {options.registration.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>,
            )}
            {paid && field("priceMin", "Cena od (zł)", input("priceMin", { type: "number", min: 0, max: 100000, step: "0.01", inputMode: "decimal" }))}
            {paid && field("priceMax", "Cena do (zł)", input("priceMax", { type: "number", min: 0, max: 100000, step: "0.01", inputMode: "decimal" }))}
            {!walkIn && field("ticketUrl", "Link do biletów / zapisów", input("ticketUrl", { type: "url", placeholder: "https://", maxLength: 500 }), { wide: true })}
          </section>

          <section className="section">
            <h2>Dla kogo i dostępność</h2>
            <p>Te informacje trafiają wprost do dopasowania – podaj tylko to, co jest prawdą.</p>
            {group(
              "audience",
              "Dla kogo",
              <div className="checks">
                {options.audience.map((o) => (
                  <button key={o} type="button" className="check" aria-pressed={form.audience.includes(o)} onClick={() => toggle("audience", o)}>
                    {o}
                  </button>
                ))}
              </div>,
              true,
            )}
            {group(
              "accessibility",
              "Dostępność",
              <div className="checks">
                {options.accessibility.map((o) => (
                  <button key={o} type="button" className="check" aria-pressed={form.accessibility.includes(o)} onClick={() => toggle("accessibility", o)}>
                    <Icon name={form.accessibility.includes(o) ? "check_box" : "check_box_outline_blank"} />
                    {o}
                  </button>
                ))}
              </div>,
              true,
            )}
          </section>

          <section className="section">
            <h2>Zdjęcie</h2>
            <div
              className={`dropzone${dragOver ? " over" : ""}${errors.has("photo") ? " invalid" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => fileInput.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                choosePhoto(e.dataTransfer.files[0]);
              }}
            >
              {photoUrl && <img src={photoUrl} alt="Podgląd zdjęcia" />}
              <span className="hint">
                <Icon name="upload" />
                {photo ? `${photo.name} · zmień` : `Przeciągnij zdjęcie lub wybierz plik · JPG, PNG, WebP do ${cfg.maxPhotoMb} MB`}
              </span>
              <input ref={fileInput} type="file" accept={PHOTO_TYPES.join(",")} onChange={(e) => choosePhoto(e.target.files?.[0])} />
            </div>
          </section>
        </div>

        <aside className="edit-aside">
          <div className="aside-title">Podgląd w aplikacji</div>
          <EventPreview
            title={form.title}
            venue={form.venue}
            address={[form.street, form.streetNumber].filter(Boolean).join(" ")}
            start={form.startsAt}
            setting={form.setting}
            price={priceText}
            free={form.cost === "Bezpłatne"}
            imageUrl={photoUrl}
          />
          <div className="info-box">
            <div className="row">
              <span>Koszt publikacji</span>
              <b>{creditsLabel(profile.eventCost)}</b>
            </div>
            <div className="row">
              <span>Twoje kredyty</span>
              <b>{profile.credits}</b>
            </div>
            <span>
              Po publikacji wydarzenie ma status „W kolejce”, a po otagowaniu przez AI (zwykle ~2 min) – „Opublikowane” i trafia do rekomendacji.
            </span>
          </div>
        </aside>
      </div>
    </div>
  );
}
