import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

// Przyciski-plakaty: ostre rogi, atrament i czerwień; po najechaniu kolory się zamieniają (bez cieni i rozjaśnień).
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap font-bold outline-none transition-[color,background-color,border-color,box-shadow] duration-200 select-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 aria-disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // atrament: główne akcje w treści (Szczegóły, Gotowe, Zaloguj się)
        default:
          "border-2 border-primary bg-primary text-primary-foreground hover:border-brand hover:bg-brand hover:text-brand-foreground",
        // czerwień Warszawy: jedna najważniejsza akcja ekranu (zakup, zapis profilu)
        brand:
          "border-2 border-brand bg-brand text-brand-foreground hover:border-primary hover:bg-primary hover:text-primary-foreground",
        outline:
          "border-2 border-input bg-transparent text-foreground hover:bg-foreground hover:text-background aria-[pressed=true]:bg-foreground aria-[pressed=true]:text-background",
        secondary: "border-2 border-secondary bg-secondary text-secondary-foreground hover:border-input",
        ghost: "text-foreground hover:bg-secondary",
        link: "h-auto p-0 text-foreground underline decoration-2 underline-offset-4 hover:text-brand-ink",
      },
      size: {
        default: "h-12 px-4 text-base",
        sm: "h-11 px-3.5 text-base",
        lg: "h-14 px-6 text-[17px] gap-2",
        xl: "h-[60px] px-8 text-lg gap-2",
        icon: "size-11",
        inline: "",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
