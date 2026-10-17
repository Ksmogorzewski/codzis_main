import { Link, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

type Props = { dark: boolean; onToggleDark: () => void; onLogout: () => void };

const navLink =
  "inline-flex h-11 items-center gap-1.5 rounded-md px-4 text-base font-semibold text-foreground outline-none transition-colors duration-200 hover:bg-secondary focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
const navActive = "bg-primary-soft text-primary-ink hover:bg-primary-soft";

export function Header({ dark, onToggleDark, onLogout }: Props) {
  // Rekomendacje są aktywne także na szczegółach wydarzenia (jak w mockupie).
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const onProfile = pathname === "/profil";
  return (
    <header className="sticky top-0 z-20 border-b bg-background">
      <div className="mx-auto flex max-w-[1160px] items-center gap-3 px-4 py-2.5 md:px-8">
        <Link
          to="/"
          className="flex items-center gap-2 rounded-md text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          <img
            src="/assets/logo.jpg"
            alt=""
            width={44}
            height={44}
            className="size-11 rounded-md bg-secondary object-cover"
          />
          <span className="text-xl font-extrabold tracking-[-0.02em]">
            Warsaw<span className="text-brand">Now</span>
          </span>
        </Link>
        <span className="flex-1" />
        <nav aria-label="Główna" className="hidden gap-1 md:flex">
          <Link to="/" className={cn(navLink, !onProfile && navActive)}>
            <Icon name="explore" />
            Rekomendacje
          </Link>
          <Link to="/profil" className={cn(navLink, onProfile && navActive)}>
            <Icon name="tune" />
            Twój profil
          </Link>
        </nav>
        <Button variant="secondary" size="icon" aria-label="Tryb ciemny" aria-pressed={dark} onClick={onToggleDark}>
          <Icon name={dark ? "light_mode" : "dark_mode"} size={22} />
        </Button>
        <Button variant="secondary" size="icon" aria-label="Wyloguj" onClick={onLogout}>
          <Icon name="logout" size={22} />
        </Button>
      </div>
    </header>
  );
}
