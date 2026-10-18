import type * as React from "react";
import { cn } from "@/lib/utils";

// Jak Input (te same tokeny i focus), dla dłuższego tekstu; wysokość zmienia użytkownik.
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-28 w-full min-w-0 resize-y rounded-lg border-[1.5px] border-input bg-card px-4 py-3 text-lg leading-snug text-foreground outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-muted-foreground/70 focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary-soft disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
