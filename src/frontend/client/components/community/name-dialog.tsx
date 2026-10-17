import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { setMissingName } from "@/lib/auth";
import { MAX_NAME, nameError } from "@/lib/auth-form";
import { meKey } from "@/lib/query-keys";

type Props = { open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void };

/**
 * Jednorazowa prośba o imię dla kont założonych przed polem „Imię” (przed pierwszym zapisem).
 * Imię trafia do Cognito; później nie da się go zmienić.
 */
export function NameDialog({ open, onOpenChange, onDone }: Props) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = nameError(name);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    const r = await setMissingName(name);
    setBusy(false);
    if (r.error !== null) {
      setError(r.error.message);
      return;
    }
    void queryClient.invalidateQueries({ queryKey: meKey() });
    onDone();
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-4 p-6 pb-[calc(24px+env(safe-area-inset-bottom))]">
        <div className="flex flex-col gap-1.5 pr-14">
          <SheetTitle>Jak masz na imię?</SheetTitle>
          <SheetDescription>
            Imię zobaczą inni zapisani na to wydarzenie. Podajesz je raz – później go nie zmienisz.
          </SheetDescription>
        </div>
        <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="missing-name">Imię</Label>
            <Input
              id="missing-name"
              autoComplete="given-name"
              placeholder="np. Anna"
              maxLength={MAX_NAME}
              value={name}
              aria-invalid={error ? true : undefined}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          {error && (
            <Alert variant="destructive">
              <Icon name="error" size={22} className="mt-px" />
              <AlertTitle className="font-semibold">{error}</AlertTitle>
            </Alert>
          )}
          <Button type="submit" size="lg" disabled={busy}>
            {busy ? "Chwileczkę…" : "Zapisz się"}
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
