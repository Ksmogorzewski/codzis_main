import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 border-2 px-4 py-3 text-base",
  {
    variants: {
      variant: {
        default: "border-input bg-card text-card-foreground",
        destructive: "border-brand bg-brand-soft text-brand-ink",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  );
}

function AlertTitle({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="alert-title" className={cn("font-bold", className)} {...props} />;
}

function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-description"
      className={cn("col-start-2 text-meta", className)}
      {...props}
    />
  );
}

export { Alert, AlertDescription, AlertTitle };
