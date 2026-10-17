import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useSave } from "@/hooks/use-save.mutation";
import { currentName } from "@/lib/auth";
import { savesLabel } from "@/lib/community";
import { cn } from "@/lib/utils";
import { NameDialog } from "./name-dialog";

type Props = {
  id: string;
  saved: boolean | undefined;
  saves: number | undefined;
  size?: "default" | "lg";
  className?: string;
};

/**
 * „Zapisz” / „Zapisano”: przełącza zapis na wydarzenie (optymistycznie, useSave). Konto bez imienia
 * przed pierwszym zapisem dostaje jednorazową prośbę o imię.
 */
export function SaveButton({ id, saved, saves, size = "default", className }: Props) {
  const save = useSave();
  const [askName, setAskName] = useState(false);
  const isSaved = saved === true;

  function toggle() {
    if (save.isPending) return; // jedno zapytanie naraz; bez disabled, żeby nie gubić fokusu
    if (!isSaved && !currentName()) {
      setAskName(true);
      return;
    }
    save.mutate({ id, save: !isSaved });
  }

  const count = saves !== undefined ? ` (${savesLabel(saves).toLowerCase()})` : "";
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size={size}
        aria-pressed={isSaved}
        aria-label={`${isSaved ? "Zapisano – wypisz się" : "Zapisz się"}${count}`}
        aria-busy={save.isPending || undefined}
        onClick={toggle}
        className={cn(isSaved && "border-primary bg-primary-soft text-primary-ink hover:border-primary", className)}
      >
        <Icon name="bookmark" size={size === "lg" ? 22 : 20} filled={isSaved} />
        {isSaved ? "Zapisano" : "Zapisz"}
      </Button>
      <NameDialog
        open={askName}
        onOpenChange={setAskName}
        onDone={() => {
          setAskName(false);
          save.mutate({ id, save: true });
        }}
      />
    </>
  );
}

/** „Zapisanych: N” przy karcie i w szczegółach; bez znanego licznika nic. */
export function SavesCount({ saves, className }: { saves: number | undefined; className?: string }) {
  if (saves === undefined) return null;
  return (
    <span className={cn("flex items-center gap-1.5", className)}>
      <Icon name="group" size={18} />
      {savesLabel(saves)}
    </span>
  );
}
