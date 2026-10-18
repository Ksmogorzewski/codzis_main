import { cva, type VariantProps } from "class-variance-authority";
import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

function Sheet(props: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetClose(props: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-overlay duration-200 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
        className,
      )}
      {...props}
    />
  );
}

const sheetVariants = cva(
  "fixed z-50 flex flex-col overflow-y-auto overscroll-contain border-t-2 border-input bg-card text-card-foreground shadow-[0_-10px_40px_rgb(0_0_0/0.25)] md:border-2 outline-none ease-[cubic-bezier(.2,.8,.2,1)] data-[state=open]:animate-in data-[state=open]:duration-[250ms] data-[state=closed]:animate-out data-[state=closed]:duration-200",
  {
    variants: {
      side: {
        bottom:
          "inset-x-0 bottom-0 max-h-[90dvh] data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom",
        // Telefon: panel od dołu. Desktop (≥ 860 px): wyśrodkowane okno 640 px.
        adaptive:
          "inset-x-0 bottom-0 max-h-[90dvh] data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom md:inset-x-auto md:bottom-auto md:top-1/2 md:left-1/2 md:w-[calc(100%-48px)] md:max-w-[640px] md:-translate-x-1/2 md:-translate-y-1/2 md:data-[state=open]:fade-in-0 md:data-[state=open]:slide-in-from-bottom-4 md:data-[state=closed]:fade-out-0 md:data-[state=closed]:slide-out-to-bottom-4",
      },
    },
    defaultVariants: { side: "adaptive" },
  },
);

function SheetContent({
  className,
  children,
  side,
  showClose = true,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> &
  VariantProps<typeof sheetVariants> & { showClose?: boolean }) {
  return (
    <SheetPrimitive.Portal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(sheetVariants({ side }), className)}
        {...props}
      >
        {children}
        {showClose && (
          <SheetPrimitive.Close className="absolute top-6 right-5 grid size-11 place-items-center border-2 border-input bg-card text-foreground outline-none transition-colors duration-200 hover:bg-foreground hover:text-background focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card">
            <XIcon className="size-[22px]" strokeWidth={2.25} aria-hidden="true" />
            <span className="sr-only">Zamknij</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("font-display text-[28px] font-extrabold leading-[1.05] tracking-[-0.01em] [font-stretch:85%]", className)}
      {...props}
    />
  );
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-base text-muted-foreground", className)}
      {...props}
    />
  );
}

export { Sheet, SheetClose, SheetContent, SheetDescription, SheetTitle };
