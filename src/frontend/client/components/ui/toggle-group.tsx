import { cva, type VariantProps } from "class-variance-authority";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

const toggleGroupVariants = cva("flex", {
  variants: {
    variant: {
      // segment czasu: szara szyna, wybrany element jako uniesiona "płytka"
      segment: "w-fit gap-0.5 rounded-[14px] bg-secondary p-1",
      // kategorie: osobne pigułki
      pill: "gap-1.5",
    },
  },
  defaultVariants: { variant: "segment" },
});

const toggleItemVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap font-semibold outline-none transition-[color,background-color,border-color,box-shadow] duration-200 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        segment:
          "h-11 rounded-[10px] px-3 text-meta text-muted-foreground hover:text-foreground data-[state=on]:bg-card data-[state=on]:text-foreground data-[state=on]:shadow-[0_1px_3px_rgb(10_14_30/0.15)]",
        pill: "h-11 rounded-full border-[1.5px] border-input bg-card px-4 text-base text-foreground hover:border-foreground data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground",
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
