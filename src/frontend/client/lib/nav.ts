// Pięć miejsc aplikacji: w nagłówku na desktopie, w dolnym pasku zakładek na telefonie.
// „Twoje” ma plakietkę z liczbą nieprzeczytanych wiadomości w czatach ekip (lib/crew-inbox.ts),
// „Znajomi” - z liczbą zaproszeń do mnie (hooks/use-friend-invites.query.ts).
// Eksploruj nie ma pozycji w menu (trasa /eksploruj zostaje: link „Zobacz wszystkie wydarzenia” na Dla Ciebie).

export const NAV_ITEMS = [
  { to: "/", label: "Dla Ciebie", icon: "home" },
  { to: "/znajomi", label: "Znajomi", icon: "diversity_3" },
  { to: "/popularne", label: "Popularne", icon: "trending_up" },
  { to: "/twoje", label: "Twoje", icon: "event_available" },
  { to: "/profil", label: "Profil", icon: "person" },
] as const;

export type NavTarget = (typeof NAV_ITEMS)[number]["to"];

/** Zakładka aktywna dla adresu (ekran zaproszenia = Znajomi); szczegóły wydarzenia (wejście z dowolnej listy) - żadna. */
export function activeTab(pathname: string): NavTarget | null {
  if (pathname.startsWith("/znajomi/")) return "/znajomi";
  return NAV_ITEMS.find((i) => i.to === pathname)?.to ?? null;
}

/** Liczba na plakietce: 0 - brak plakietki (null), powyżej `max` - „9+” / „99+”. */
export function badgeText(count: number, max: number): string | null {
  if (count <= 0) return null;
  return count > max ? `${max}+` : String(count);
}
