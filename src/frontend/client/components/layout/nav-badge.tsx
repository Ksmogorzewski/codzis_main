import { unreadLabel } from "@/lib/crew-inbox";
import { cn } from "@/lib/utils";

/**
 * Plakietka z liczbą nieprzeczytanych wiadomości (czaty ekip, DEMO) przy „Twoje” i na liście czatów.
 * Liczba jest tylko wizualna; czytnik dostaje pełny podpis („3 nowe wiadomości”).
 */
export function UnreadBadge({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <>
      <span
        aria-hidden="true"
        className={cn(
          "inline-grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-xs leading-none font-bold text-brand-foreground tabular-nums",
          className,
        )}
      >
        {count > 99 ? "99+" : count}
      </span>
      <span className="sr-only">{`, ${unreadLabel(count)}`}</span>
    </>
  );
}
