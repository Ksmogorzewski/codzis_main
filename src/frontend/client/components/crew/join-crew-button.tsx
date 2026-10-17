import { useState } from "react";
import { NameDialog } from "@/components/community/name-dialog";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useSave } from "@/hooks/use-save.mutation";
import { currentName } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Czat ekipy jest dla zapisanych: ten przycisk zapisuje na wydarzenie (ten sam useSave co „Zapisz”,
 * optymistycznie) — po zapisie wejście na czat pojawia się od razu. Konto bez imienia najpierw podaje imię.
 */
export function JoinCrewButton({ id, className }: { id: string; className?: string }) {
  const save = useSave();
  const [askName, setAskName] = useState(false);

  function join() {
    if (save.isPending) return;
    if (!currentName()) {
      setAskName(true);
      return;
    }
    save.mutate({ id, save: true });
  }

  return (
    <>
      <Button
        type="button"
        size="lg"
        aria-busy={save.isPending || undefined}
        onClick={join}
        className={cn("h-auto min-h-14 py-3 text-center whitespace-normal", className)}
      >
        <Icon name="bookmark_add" size={22} />
        Zapisz się, żeby dołączyć do czatu ekipy
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
