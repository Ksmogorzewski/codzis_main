import { Icon } from "../../shared/Icon";
import { formatDayLabel } from "../../shared/format";
import type { Me, OnboardingStep } from "../lib/types";
import { isFilled, summary } from "../lib/wizard";
import { Recommendations } from "./Recommendations";

type Props = { me: Me; steps: OnboardingStep[] };

// Zakładka "Rekomendacje": nagłówek dnia, propozycje z RAG i podsumowanie profilu, na którym się opierają
export function Home({ me, steps }: Props) {
  const answers = me.profile?.answers ?? {};
  const prefs = me.profile?.preferences;
  const firstName = me.name?.split(" ")[0];
  const headline = steps
    .filter((s) => s.id === "who" || s.id === "vibe")
    .flatMap((s) => summary(s, answers))
    .slice(0, 3)
    .join(" · ");

  return (
    <main className="page">
      <section className="day-hero">
        <div className="day-label">
          {formatDayLabel()}
          {prefs?.district ? ` · ${prefs.district}` : ""}
        </div>
        <div className="day-title">{firstName ? `Cześć, ${firstName}! Co robimy dziś?` : "Co robimy dziś?"}</div>
        <p className="day-profile">Propozycje dla profilu: {headline || "uzupełnij profil"}</p>
      </section>

      <Recommendations />

      <details className="card prefs-card">
        <summary className="card-head">
          <h2>Na tej podstawie dobieramy propozycje</h2>
          <Icon name="expand_more" className="prefs-chevron" />
        </summary>
        <div className="prefs">
          {steps
            .filter((s) => isFilled(s, answers))
            .map((s) => (
              <div className="pref-row" key={s.id}>
                <span className="tile-icon">
                  <Icon name={s.icon} fill />
                </span>
                <div className="pref-body">
                  <span className="pref-title">{s.title}</span>
                  <div className="tile-foot">
                    {summary(s, answers).map((label) => (
                      <span className="chip-ok" key={label}>
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
        </div>
        <div className="row-gap prefs-actions">
          <a className="btn btn-outline btn-sm" href="#/profil">
            <Icon name="edit" />
            Edytuj profil
          </a>
        </div>
        {me.profile?.ragProfile && (
          <details className="rag">
            <summary>Parametry do rekomendacji</summary>
            <pre>{me.profile.ragProfile}</pre>
          </details>
        )}
      </details>
    </main>
  );
}
