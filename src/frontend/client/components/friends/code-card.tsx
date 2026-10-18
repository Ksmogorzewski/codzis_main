import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { useRegenerateCode } from "@/hooks/use-friend-actions.mutation";
import { inviteLink } from "@/lib/friends";
import { cn } from "@/lib/utils";
import { ConfirmSheet } from "./confirm-sheet";
import { QrCode } from "./qr-code";

/** Link z QR: adres tej samej strony (origin + ścieżka z window.location), nie wpisany na sztywno. */
const linkFor = (code: string) => inviteLink(code, window.location.origin, window.location.pathname);

async function copy(link: string) {
  try {
    await navigator.clipboard.writeText(link);
    toast("Skopiowano link");
  } catch {
    toast(`Skopiuj link ręcznie: ${link}`);
  }
}

type Props = { code: string; large?: boolean; className?: string };

/**
 * „Twój kod”: kod do podyktowania, QR z linkiem (skanuje się go aparatem telefonu), „Kopiuj link”
 * i „Nowy kod” (z potwierdzeniem: stary przestaje działać, znajomi zostają).
 */
export function CodeCard({ code, large = false, className }: Props) {
  const regenerate = useRegenerateCode();
  const [confirm, setConfirm] = useState(false);
  const link = linkFor(code);

  return (
    <Card className={cn("items-center gap-4 p-5 text-center", className)}>
      <h2 className="self-start text-xl font-extrabold">Twój kod</h2>
      <QrCode
        value={link}
        label={`Kod QR z zaproszeniem do znajomych, kod ${code}`}
        className={large ? "w-full max-w-[280px]" : "w-full max-w-[200px]"}
      />
      <p className="flex flex-col gap-0.5">
        <span className="text-meta text-muted-foreground">Kod do podyktowania</span>
        <span className="font-mono text-[28px] leading-tight font-extrabold tracking-[0.08em] tabular-nums">{code}</span>
      </p>
      <div className="flex w-full flex-col gap-2">
        <Button onClick={() => void copy(link)}>
          <Icon name="content_copy" />
          Kopiuj link
        </Button>
        <Button variant="ghost" aria-busy={regenerate.isPending || undefined} onClick={() => setConfirm(true)}>
          <Icon name="refresh" />
          Nowy kod
        </Button>
      </div>
      <ConfirmSheet
        open={confirm}
        onOpenChange={setConfirm}
        title="Utworzyć nowy kod?"
        description="Stary kod i QR przestaną działać. Obecni znajomi zostają, a wysłane już zaproszenia są nadal ważne."
        confirm="Nowy kod"
        onConfirm={() => regenerate.mutate()}
      />
    </Card>
  );
}
