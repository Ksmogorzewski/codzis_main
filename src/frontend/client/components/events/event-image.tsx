import { type CSSProperties, type ReactNode, useState } from "react";
import { safeUrl, tint } from "@/lib/events";
import { cn } from "@/lib/utils";

type Props = {
  id: string;
  imageUrl: string | null;
  /** Szerokość pasków tła zastępczego (karta 10 px, szczegóły 14 px jak w mockupie). */
  stripe: 10 | 14;
  lazy?: boolean;
  className?: string;
  children?: ReactNode;
};

const STRIPES = {
  10: "bg-[repeating-linear-gradient(135deg,var(--tint)_0_10px,transparent_10px_20px)]",
  14: "bg-[repeating-linear-gradient(135deg,var(--tint)_0_14px,transparent_14px_28px)]",
} as const;

/**
 * Zdjęcie wydarzenia albo tło w paski w stałym odcieniu z id (jak w mockupie).
 * Zepsuty adres obrazka chowa <img>, zostaje tło. Tylko http(s).
 */
export function EventImage({ id, imageUrl, stripe, lazy, className, children }: Props) {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : safeUrl(imageUrl);
  return (
    <div
      className={cn("relative overflow-hidden bg-secondary", STRIPES[stripe], className)}
      // jedyna wartość liczona z danych: odcień paska (token koloru nie ma sensu dla hasha id)
      style={{ "--tint": tint(id) } as CSSProperties}
    >
      {src && (
        <img
          src={src}
          alt=""
          loading={lazy ? "lazy" : undefined}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="absolute inset-0 size-full object-cover"
        />
      )}
      {children && <div className="absolute inset-x-3 top-3 flex flex-wrap gap-1.5">{children}</div>}
    </div>
  );
}
