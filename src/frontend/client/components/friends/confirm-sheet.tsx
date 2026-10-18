import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirm: string;
  onConfirm: () => void;
};

/** Potwierdzenie akcji, której nie da się cofnąć (usunięcie znajomego, nowy kod). */
export function ConfirmSheet({ open, onOpenChange, title, description, confirm, onConfirm }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-4 p-6 pb-[calc(24px+env(safe-area-inset-bottom))]">
        <div className="flex flex-col gap-1.5 pr-14">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </div>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" size="lg" onClick={() => onOpenChange(false)}>
            Anuluj
          </Button>
          <Button
            variant="brand"
            size="lg"
            onClick={() => {
              onOpenChange(false);
              onConfirm();
            }}
          >
            {confirm}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
