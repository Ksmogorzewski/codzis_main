import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

// Plakietki: prostokąty bez zaokrągleń, jak naklejki na plakacie.
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 whitespace-nowrap font-bold leading-none",
  {
    variants: {
      variant: {
        // na kolorowym polu plakatu / zdjęciu
        surface: "bg-background text-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        // znacznik stanu: "Darmowe", wybrane odpowiedzi ankiety
        success: "bg-success-soft text-success-ink",
        brand: "bg-brand text-brand-foreground",
      },
      size: {
        default: "px-2 py-[5px] text-[13px]",
        lg: "px-2.5 py-1.5 text-sm",
        price: "px-2.5 py-1 text-meta",
      },
    },
    defaultVariants: { variant: "secondary", size: "default" },
  },
);

function Badge({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
