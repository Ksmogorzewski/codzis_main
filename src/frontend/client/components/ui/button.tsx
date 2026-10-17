import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap font-bold outline-none transition-[color,background-color,border-color,box-shadow,filter] duration-200 select-none focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 aria-disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // granat: główne akcje w treści (Bilet, Gotowe, Pokaż wszystko)
        default: "bg-primary text-primary-foreground hover:brightness-115",
        // czerwień Warszawy: jedna najważniejsza akcja ekranu (logowanie, zakup, rekomendacje)
        brand: "bg-brand text-brand-foreground hover:brightness-108",
        outline:
          "border-[1.5px] border-input bg-card text-foreground hover:border-foreground aria-[pressed=true]:border-primary",
        secondary: "bg-secondary text-secondary-foreground hover:bg-border",
        ghost: "text-foreground hover:bg-secondary",
        link: "h-auto rounded-sm p-0 text-brand-ink underline-offset-4 hover:text-foreground hover:underline",
      },
      size: {
        default: "h-12 rounded-lg px-4 text-base",
        sm: "h-11 rounded-md px-3.5 text-base",
        lg: "h-14 rounded-lg px-6 text-[17px] gap-2",
        xl: "h-[60px] rounded-xl px-8 text-lg gap-2",
        icon: "size-11 rounded-md",
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
