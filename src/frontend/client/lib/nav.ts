// Cztery miejsca aplikacji: w nagłówku na desktopie, w dolnym pasku zakładek na telefonie.

export const NAV_ITEMS = [
  { to: "/", label: "Dla Ciebie", icon: "home" },
  { to: "/eksploruj", label: "Eksploruj", icon: "explore" },
  { to: "/popularne", label: "Popularne", icon: "trending_up" },
  { to: "/profil", label: "Profil", icon: "person" },
] as const;

export type NavTarget = (typeof NAV_ITEMS)[number]["to"];

/** Zakładka aktywna dla adresu; szczegóły wydarzenia (wejście z dowolnej listy) - żadna. */
export function activeTab(pathname: string): NavTarget | null {
  return NAV_ITEMS.find((i) => i.to === pathname)?.to ?? null;
}
