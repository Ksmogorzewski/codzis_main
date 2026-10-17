import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

// DEMO: czat ekipy nie ma jeszcze backendu (lib/crew-demo.ts). Ta notka musi być widoczna wszędzie,
// gdzie pokazujemy symulowane wiadomości, żeby nikt nie wziął ich za prawdziwe osoby.
export function DemoNote({ className }: { className?: string }) {
  return (
    <p className={cn("flex items-center gap-1.5 text-sm font-semibold text-warning-ink", className)}>
      <Icon name="info" size={18} />
      Podgląd czatu (demo) — wiadomości ekipy są symulowane.
    </p>
  );
}
