import type * as React from "react";
import { cn } from "@/lib/utils";

type Props = Omit<React.ComponentProps<"span">, "children"> & {
  /** Nazwa ikony Material Symbols Rounded, np. "location_on". */
  name: string;
  /** Rozmiar w px. Podany w style, bo arkusz Google Fonts (poza warstwami) wygrywa z klasami. */
  size?: number;
  filled?: boolean;
};

/** Ikony z mockupu (Material Symbols Rounded). Dekoracyjne: tekst obok niesie znaczenie. */
function Icon({ name, size = 20, filled = false, className, style, ...props }: Props) {
  return (
    <span
      aria-hidden="true"
      translate="no"
      className={cn("material-symbols-rounded shrink-0 select-none", className)}
      style={{
        fontSize: size,
        fontVariationSettings: filled ? "'FILL' 1" : undefined,
        ...style,
      }}
      {...props}
    >
      {name}
    </span>
  );
}

export { Icon };
