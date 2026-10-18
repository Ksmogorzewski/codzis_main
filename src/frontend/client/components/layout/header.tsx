import { Link, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useCrewUnreadTotal } from "@/hooks/use-crew-unread";
import { useFriendInvitesCount } from "@/hooks/use-friend-invites.query";
import { invitesLabel } from "@/lib/friends";
import { activeTab, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { UnreadBadge } from "./nav-badge";

type Props = { dark: boolean; onToggleDark: () => void; onLogout: () => void };

const focusRing =
  "outline-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";
// Same napisy (bez ikon; ikony ma dolny pasek na telefonie). Do 1100 px ciaśniej, żeby pięć miejsc się zmieściło.
const navLink = cn(
  "inline-flex h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap px-2 text-[15px] font-semibold text-foreground underline decoration-transparent decoration-[3px] underline-offset-[7px] transition-[text-decoration-color] duration-200 hover:decoration-border min-[1100px]:px-3 min-[1100px]:text-[17px]",
  focusRing,
);
const navActive = "decoration-foreground hover:decoration-foreground";

export function Header({ dark, onToggleDark, onLogout }: Props) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const active = activeTab(pathname);
  const unread = useCrewUnreadTotal();
  const invites = useFriendInvitesCount();
  return (
    <header className="sticky top-0 z-20 border-b-2 border-input bg-background pt-[env(safe-area-inset-top)]">
      <div className="mx-auto flex min-h-[68px] max-w-[1160px] items-center gap-2 px-4 md:gap-3 md:px-8">
        <Link
          to="/"
          className={cn(
            "font-display text-[23px] leading-none font-black tracking-[-0.02em] text-foreground [font-stretch:130%] md:text-[27px]",
            focusRing,
          )}
        >
          WarsawNow
        </Link>
        <span className="flex-1" />
        {/* Na telefonie te same miejsca są w dolnym pasku (tab-bar.tsx). */}
        <nav aria-label="Główna" className="hidden gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              aria-current={active === item.to ? "page" : undefined}
              className={cn(navLink, active === item.to && navActive)}
            >
              {item.label}
              {item.to === "/twoje" && <UnreadBadge count={unread} />}
              {item.to === "/znajomi" && <UnreadBadge count={invites} label={invitesLabel} max={9} />}
            </Link>
          ))}
        </nav>
        <Button variant="outline"
          size="icon"
          aria-label="Tryb ciemny"
          aria-pressed={dark}
          onClick={onToggleDark}
          className="aria-[pressed=true]:bg-transparent aria-[pressed=true]:text-foreground aria-[pressed=true]:hover:bg-foreground aria-[pressed=true]:hover:text-background"
        >
          <Icon name={dark ? "light_mode" : "dark_mode"} size={22} />
        </Button>
        <Button variant="outline" size="icon" aria-label="Wyloguj" onClick={onLogout}>
          <Icon name="logout" size={22} />
        </Button>
      </div>
    </header>
  );
}
