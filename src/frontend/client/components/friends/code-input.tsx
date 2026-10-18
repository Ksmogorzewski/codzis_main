import { useNavigate } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { normalizeCode } from "@/lib/friends";
import { cn } from "@/lib/utils";

/** „Wpisz kod znajomego”: kod wpisany byle jak (np. „waw 7k2p9x”) prowadzi na ekran zaproszenia. */
export function CodeInput({ className }: { className?: string }) {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const code = normalizeCode(value);
    if (!code) {
      setError("Kod ma postać WAW-XXXXXX (6 liter i cyfr po WAW).");
      return;
    }
    setError(null);
    void navigate({ to: "/znajomi/dodaj/$code", params: { code } });
  }

  return (
    <Card className={cn("gap-3 p-5", className)}>
      <form className="flex flex-col gap-3" onSubmit={submit} noValidate>
        <Label htmlFor="friend-code" className="text-xl font-extrabold">
          Wpisz kod znajomego
        </Label>
        <div className="flex gap-2">
          <Input
            id="friend-code"
            placeholder="WAW-7K2P9X"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={16}
            value={value}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "friend-code-error" : undefined}
            onChange={(e) => setValue(e.target.value)}
            className="min-w-0 flex-1 font-mono uppercase"
          />
          <Button type="submit" size="lg">
            Dalej
          </Button>
        </div>
        {error && (
          <p id="friend-code-error" className="text-meta font-semibold text-brand-ink">
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}
