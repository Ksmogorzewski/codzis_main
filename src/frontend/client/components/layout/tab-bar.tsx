import { Link, useRouterState } from "@tanstack/react-router";
import { Icon } from "@/components/ui/icon";
import { useCrewUnreadTotal } from "@/hooks/use-crew-unread";
import { useFriendInvitesCount } from "@/hooks/use-friend-invites.query";
import { invitesLabel } from "@/lib/friends";
import { activeTab, NAV_ITEMS } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { UnreadBadge } from "./nav-badge";

const badgeCorner = "absolute -top-1 right-0 ring-2 ring-background";

/**
 * Dolny pasek zakładek na telefonie (na desktopie te same linki są w nagłówku). Pięć zakładek mieści się
 * od 360 px (72 px na zakładkę); „Twoje” z plakietką nieprzeczytanych wiadomości w czatach ekip,
 * „Znajomi” z liczbą zaproszeń.
 */
export function TabBar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const active = activeTab(pathname);
  const unread = useCrewUnreadTotal();
  const invites = useFriendInvitesCount();
  return (
    <nav
      aria-label="Główna"
      className="fixed inset-x-0 bottom-0 z-20 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="mx-auto grid max-w-[560px] grid-cols-5">
        {NAV_ITEMS.map((item) => {
          const on = active === item.to;
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "flex min-h-14 flex-col items-center justify-center gap-0.5 px-0.5 py-1.5 text-[13px] font-semibold whitespace-nowrap text-muted-foreground outline-none transition-colors duration-200 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-inset",
                  on && "text-primary-ink",
                )}
              >
                <span
                  className={cn(
                    "relative grid h-8 w-14 place-items-center rounded-full transition-colors duration-200",
                    on && "bg-primary-soft",
                  )}
                >
                  <Icon name={item.icon} size={22} filled={on} />
                  {item.to === "/twoje" && <UnreadBadge count={unread} className={badgeCorner} />}
                  {item.to === "/znajomi" && (
                    <UnreadBadge count={invites} label={invitesLabel} max={9} className={badgeCorner} />
                  )}
                </span>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
