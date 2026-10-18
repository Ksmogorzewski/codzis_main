import { Icon } from "../../shared/Icon";
import { initials } from "../../shared/format";
import type { Screen } from "../App";
import { googleLogin } from "../lib/auth";
import type { Profile } from "../lib/types";

type Props = { profile: Profile; active: Screen; eventsCount: number | null; onLogout: () => void };

export function Sidebar({ profile, active, eventsCount, onLogout }: Props) {
  const item = (screen: Screen, icon: string, label: string, count?: string | number | null) => (
    <a href={`#/${screen}`} aria-current={active === screen ? "page" : undefined}>
      <Icon name={icon} />
      <span className="label">{label}</span>
      {count != null && <span className="count">{count}</span>}
    </a>
  );
  // Pasek: ile ogłoszeń wystarczy na obecne kredyty (do 10 dla czytelności)
  const capacity = Math.floor(profile.credits / Math.max(profile.eventCost, 1));

  return (
    <aside className="side">
      <div className="side-brand">
        <img src="/assets/logo.jpg" alt="" />
        <span>
          <b>WarsawNow</b>
          <small>Organizator</small>
        </span>
        <button className="side-logout side-mobile-logout" type="button" onClick={onLogout} aria-label="Wyloguj">
          <Icon name="logout" size={18} />
        </button>
      </div>
      <nav className="side-nav" aria-label="Nawigacja">
        {item("wydarzenia", "event_note", "Moje wydarzenia", eventsCount)}
        {item("dodaj", "add_circle", "Dodaj wydarzenie")}
        {item("platnosci", "payments", "Płatności i kredyty", profile.credits)}
      </nav>
      <span className="side-spacer" />
      <div className="side-credits">
        <div className="row">
          <span>Kredyty</span>
          <span className="value">{profile.credits}</span>
        </div>
        <div className="bar">
          <div style={{ width: `${Math.min(capacity, 10) * 10}%` }} />
        </div>
        <div className="row">
          <span>wystarczy na {capacity} ogł.</span>
          <a href="#/platnosci">Doładuj</a>
        </div>
      </div>
      <div className="side-user">
        <span className="avatar">{initials(profile.partnerName)}</span>
        <span className="who">
          <b>{profile.partnerName}</b>
          {/* Przy Google partnerId to długi identyfikator Cognito - zamiast niego rodzaj konta */}
          <small>{googleLogin() ? "Konto Google" : profile.partnerId}</small>
        </span>
        <button className="side-logout" type="button" onClick={onLogout} aria-label="Wyloguj">
          <Icon name="logout" size={18} />
        </button>
      </div>
    </aside>
  );
}
