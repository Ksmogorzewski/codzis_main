import { Icon } from "../../shared/Icon";
import { config } from "../lib/config";
import { AuthCard } from "./AuthCard";

type Props = { initialError?: string; onSignedIn: () => void };

const HOW = [
  { icon: "person_add", title: "Załóż konto", text: "E-mailem albo kontem Google – zajmie to chwilę." },
  { icon: "tune", title: "Powiedz, co lubisz", text: "Kilka kafelków: z kim wychodzisz, na jaki klimat masz ochotę, gdzie i kiedy." },
  { icon: "auto_awesome", title: "Odbieraj propozycje", text: "Wydarzenia dopasowane do profilu, okolicy i pogody – z wyjaśnieniem, dlaczego pasują." },
];
const SOURCES = [
  { icon: "event", title: "Kalendarz miasta", text: "Oficjalny kalendarz wydarzeń m.st. Warszawy – kultura, edukacja, święta miejskie." },
  { icon: "sports_soccer", title: "Zajęcia sportowe", text: "Bezpłatne i płatne zajęcia z miejskiego kalendarza sportu – od fitnessu po pływanie." },
  { icon: "storefront", title: "Lokalni organizatorzy", text: "Koncerty, warsztaty i spotkania od organizatorów – z ceną, biletami i dostępnością." },
];

function Cards({ items }: { items: typeof HOW }) {
  return (
    <div className="steps-grid">
      {items.map((item) => (
        <article className="step-card" key={item.title}>
          <span className="step-icon">
            <Icon name={item.icon} fill size={30} />
          </span>
          <h3>{item.title}</h3>
          <p>{item.text}</p>
        </article>
      ))}
    </div>
  );
}

export function Landing({ initialError, onSignedIn }: Props) {
  return (
    <>
      <div className="auth">
        <section className="auth-hero">
          <span className="hero-circle" aria-hidden="true" />
          <span className="hero-ring" aria-hidden="true" />
          <div className="brand brand-light">
            <img src="/assets/logo.jpg" alt="" className="brand-logo brand-logo-lg" />
            <span className="brand-name">
              Warsaw<b>Now</b>
            </span>
          </div>
          <div className="hero-copy">
            <h1>Wiesz, co robić w Warszawie dziś</h1>
            <p>Propozycje na wolny czas dopasowane do Ciebie i Twojej okolicy.</p>
            <ul className="hero-points">
              <li><Icon name="auto_awesome" fill />Dopasowane do Twojego profilu</li>
              <li><Icon name="near_me" fill />Blisko Ciebie – w Twojej dzielnicy</li>
              <li><Icon name="partly_cloudy_day" fill />Z myślą o pogodzie i jakości powietrza</li>
            </ul>
          </div>
          <a className="hero-more" href="#jak-to-dziala" onClick={(e) => {
            e.preventDefault();
            document.getElementById("jak-to-dziala")?.scrollIntoView({ behavior: "smooth" });
          }}>
            Jak to działa <Icon name="south" />
          </a>
        </section>
        <section className="auth-panel">
          <AuthCard initialError={initialError} onSignedIn={onSignedIn} />
        </section>
      </div>

      <section id="jak-to-dziala" className="overview">
        <div className="overview-inner">
          <div className="eyebrow">Jak to działa</div>
          <h2>Trzy kroki do planu na dziś</h2>
          <Cards items={HOW} />
          <div className="eyebrow">Skąd bierzemy wydarzenia</div>
          <h2>Cała Warszawa w jednym miejscu</h2>
          <Cards items={SOURCES} />
          <div className="org-band">
            <div>
              <h3>Organizujesz wydarzenia?</h3>
              <p>Dodawaj je w panelu organizatora i docieraj do osób, którym naprawdę pasują.</p>
            </div>
            <a className="btn btn-white" href={config().partnerPortal}>
              Panel organizatora <Icon name="arrow_forward" />
            </a>
          </div>
        </div>
        <footer className="footer">
          <span>© WarsawNow</span>
          <span>
            Dane o wydarzeniach: Urząd m.st. Warszawy, <a href="https://dane.um.warszawa.pl" rel="noopener">dane.um.warszawa.pl</a> (CC BY)
          </span>
        </footer>
      </section>
    </>
  );
}
