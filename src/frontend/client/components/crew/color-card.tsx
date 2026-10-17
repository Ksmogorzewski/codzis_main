import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";

// Pełny ekran w czerwieni Warszawy do pokazania grupie w tłumie. Esc albo przycisk wraca do czatu.
export function ColorCard({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <section
      aria-label="Karta koloru"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-brand p-6 text-center text-brand-foreground motion-safe:animate-pop"
    >
      <Icon name="location_on" size={64} filled />
      <h2 className="text-[44px] leading-[1.05] font-extrabold tracking-[-0.02em]">
        JESTEM
        <br />
        TUTAJ
      </h2>
      <p className="text-lg leading-snug">
        Pokaż ten ekran
        <br />
        swojej grupie.
      </p>
      <Button
        autoFocus
        onClick={onClose}
        className="mt-8 bg-brand-foreground px-5 text-brand hover:brightness-95 focus-visible:ring-brand-foreground focus-visible:ring-offset-brand"
      >
        <Icon name="arrow_back" size={22} />
        Wróć do czatu
      </Button>
    </section>
  );
}
