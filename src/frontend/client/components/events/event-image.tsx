import { type ReactNode, useState } from "react";
import type { Category } from "@/lib/categories";
import { safeUrl } from "@/lib/events";
import { cn } from "@/lib/utils";
import { POSTER_FIELD } from "./poster-tone";

type Props = {
  imageUrl: string | null;
  category: Exclude<Category, "all">;
  /** Karta: zdjęcie w duotonie na kolorze kategorii (jak druk plakatu). Szczegóły: zdjęcie w naturalnych kolorach. */
  duotone?: boolean;
  lazy?: boolean;
  /** Adres zdjęcia nie działa (karta przestaje wtedy odsłaniać zdjęcie). */
  onFailed?: () => void;
  className?: string;
  children?: ReactNode;
};

/**
 * Zdjęcie wydarzenia na polu w kolorze kategorii. Bez zdjęcia (albo z zepsutym adresem) nie renderuje nic –
 * plakat karty i nagłówek szczegółów same niosą kolor i tytuł. Tylko http(s).
 */
export function EventImage({ imageUrl, category, duotone, lazy, onFailed, className, children }: Props) {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : safeUrl(imageUrl);
  if (!src) return null;
  return (
    <div className={cn("relative overflow-hidden", POSTER_FIELD[category], className)}>
      <img
        src={src}
        alt=""
        loading={lazy ? "lazy" : undefined}
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => {
          setFailed(true);
          onFailed?.();
        }}
        className={cn("absolute inset-0 size-full object-cover", duotone && "contrast-125 grayscale mix-blend-multiply")}
      />
      {children && <div className="absolute inset-x-3 top-3 flex flex-wrap gap-1.5">{children}</div>}
    </div>
  );
}
