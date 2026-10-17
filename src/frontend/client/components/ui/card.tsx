import type * as React from "react";
import { cn } from "@/lib/utils";

// Karta bez cienia: od tła odróżnia ją kolor powierzchni i cienka ramka (cień tylko na sheet/toast).
function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col overflow-hidden rounded-2xl border bg-card text-card-foreground",
        className,
      )}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("p-4 md:p-5", className)} {...props} />;
}

function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return (
    <h3
      data-slot="card-title"
      className={cn("text-title font-bold text-pretty", className)}
      {...props}
    />
  );
}

export { Card, CardContent, CardTitle };
