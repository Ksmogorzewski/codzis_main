import { Icon } from "../../shared/Icon";
import { formatDayLabel } from "../../shared/format";
import type { Me, OnboardingStep } from "../lib/types";
import { isFilled, summary } from "../lib/wizard";

type Props = { me: Me; steps: OnboardingStep[] };

// Do czasu uruchomienia rekomendacji (RAG): nagłówek dnia + podsumowanie zapisanego profilu
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

      <section className="soon">
        <span className="soon-icon">
          <Icon name="auto_awesome" fill />
        </span>
        <div>
          <h2>Rekomendacje są w przygotowaniu</h2>
          <p>
            Twój profil jest zapisany. Gdy uruchomimy dopasowanie, pojawią się tu wydarzenia z kalendarza miasta, zajęć sportowych i od
            organizatorów – z wyjaśnieniem, dlaczego pasują.
          </p>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Co wiemy o Twoich preferencjach</h2>
          <a className="btn btn-outline btn-sm" href="#/profil">
            <Icon name="edit" />
            Edytuj
          </a>
        </div>
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
        {me.profile?.ragProfile && (
          <details className="rag">
            <summary>Parametry do rekomendacji</summary>
            <pre>{me.profile.ragProfile}</pre>
          </details>
        )}
      </section>
    </main>
  );
}
