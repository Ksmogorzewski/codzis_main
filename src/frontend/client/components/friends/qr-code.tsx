import { useMemo } from "react";
import { encode } from "uqr";
import { qrPath } from "@/lib/friends";
import { cn } from "@/lib/utils";

/**
 * Kod QR jako SVG (biblioteka uqr: tylko macierz modułów, rysujemy sami - bez innerHTML). Zawsze ciemne
 * moduły na białym tle, także w trybie ciemnym: aparat telefonu musi go odczytać.
 */
export function QrCode({ value, label, className }: { value: string; label: string; className?: string }) {
  const { size, d } = useMemo(() => {
    const qr = encode(value, { ecc: "M", border: 2 });
    return { size: qr.size, d: qrPath(qr.data) };
  }, [value]);

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${size} ${size}`}
      shapeRendering="crispEdges"
      className={cn("aspect-square rounded-xl bg-white", className)}
    >
      <path d={d} className="fill-primary-deep" />
    </svg>
  );
}
