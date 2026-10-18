import { unreadLabel } from "@/lib/crew-inbox";
import { badgeText } from "@/lib/nav";
import { cn } from "@/lib/utils";

type Props = {
  count: number;
  className?: string;
  /** Pełny podpis dla czytnika (domyślnie „3 nowe wiadomości”). */
  label?: (count: number) => string;
  /** Powyżej tej liczby „max+” (domyślnie 99+). */
  max?: number;
};

/**
 * Plakietka z liczbą: nieprzeczytane wiadomości (czaty ekip, DEMO) przy „Twoje” i na liście czatów,
 * zaproszenia przy „Znajomi”. Liczba jest tylko wizualna; czytnik dostaje pełny podpis („3 nowe wiadomości”).
 */
export function UnreadBadge({ count, className, label = unreadLabel, max = 99 }: Props) {
  const text = badgeText(count, max);
  if (text === null) return null;
  return (
    <>
      <span
        aria-hidden="true"
        className={cn(
          "inline-grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs leading-none font-bold text-brand-foreground tabular-nums",
          className,
        )}
      >
        {text}
      </span>
      <span className="sr-only">{`, ${label(count)}`}</span>
    </>
  );
}
