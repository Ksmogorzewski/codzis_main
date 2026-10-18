import { cva, type VariantProps } from "class-variance-authority";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

const toggleGroupVariants = cva("flex", {
  variants: {
    variant: {
      // czas (Dziś / Jutro…): słowa w kroju plakatu, wybrane w odwróconym kolorze
      segment: "w-fit gap-1",
      // kategorie: tekst z kwadratem koloru, wybrana podkreślona
      pill: "gap-x-1 gap-y-1",
    },
  },
  defaultVariants: { variant: "segment" },
});

const toggleItemVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap outline-none transition-[color,background-color,border-color,text-decoration-color] duration-200 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        segment:
          "h-12 border-2 border-transparent px-3.5 font-display text-lg font-bold text-foreground [font-stretch:90%] hover:border-input data-[state=on]:border-input data-[state=on]:bg-foreground data-[state=on]:text-background md:px-4 md:text-xl",
        pill: "h-11 px-2.5 text-[17px] font-semibold text-foreground decoration-transparent underline decoration-[3px] underline-offset-[7px] hover:decoration-border data-[state=on]:decoration-foreground",
      },
    },
    defaultVariants: { variant: "segment" },
  },
);

type Variant = VariantProps<typeof toggleGroupVariants>["variant"];
const ToggleGroupContext = React.createContext<Variant>("segment");

function ToggleGroup({
  className,
  variant,
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root> &
  VariantProps<typeof toggleGroupVariants>) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      data-variant={variant}
      className={cn(toggleGroupVariants({ variant }), className)}
      {...props}
    >
      <ToggleGroupContext.Provider value={variant}>{children}</ToggleGroupContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  const variant = React.useContext(ToggleGroupContext);
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(toggleItemVariants({ variant }), className)}
      {...props}
    />
  );
}

export { ToggleGroup, ToggleGroupItem };
