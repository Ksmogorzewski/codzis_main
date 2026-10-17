import { Icon } from "../../shared/Icon";
import { useTheme } from "../lib/theme";

type Props = { active: "home" | "survey"; onLogout: () => void };

export function Header({ active, onLogout }: Props) {
  const [theme, toggleTheme] = useTheme();
  const link = (target: Props["active"], href: string, icon: string, label: string) => (
    <a href={href} aria-current={active === target ? "page" : undefined}>
      <Icon name={icon} />
      <span className="nav-label">{label}</span>
    </a>
  );

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a className="brand" href="#/rekomendacje">
          <img src="/assets/logo.jpg" alt="" className="brand-logo" />
          <span className="brand-name">
            Warsaw<b>Now</b>
          </span>
        </a>
        <span className="spacer" />
        <nav className="nav" aria-label="Nawigacja">
          {link("home", "#/rekomendacje", "explore", "Rekomendacje")}
          {link("survey", "#/profil", "tune", "Twój profil")}
        </nav>
        <button className="icon-btn" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? "Tryb jasny" : "Tryb ciemny"}>
          <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} />
        </button>
        <button className="icon-btn" type="button" onClick={onLogout} aria-label="Wyloguj">
          <Icon name="logout" />
        </button>
      </div>
    </header>
  );
}
