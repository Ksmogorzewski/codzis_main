import type { ReactNode } from "react";

type Props = {
  title: ReactNode;
  /** Mały napis nad tytułem (wersaliki, czerwień Warszawy), np. „Twój profil”. */
  eyebrow?: ReactNode;
  /** Zdanie pod tytułem. */
  children?: ReactNode;
};

/**
 * Nagłówek ekranu w kierunku „Plakat”: tytuł jak na plakacie (Anybody, wersaliki, zwężony), pod nim zdanie
 * w kroju tekstu. Jeden wzór dla ekranów z listą (Twoje, Znajomi, Popularne, Eksploruj) i ankiety; ekran główny
 * i szczegóły mają własne pole plakatu.
 */
export function PageHeader({ title, eyebrow, children }: Props) {
  return (
    <header className="flex flex-col gap-2">
      {eyebrow && <p className="text-meta font-bold tracking-[0.04em] text-brand-ink uppercase">{eyebrow}</p>}
      <h1 className="max-w-[18ch] font-display text-[44px] leading-[0.92] font-black text-balance uppercase [font-stretch:62%] md:text-[72px]">
        {title}
      </h1>
      {children && <p className="text-[17px] leading-[1.45] text-pretty text-muted-foreground">{children}</p>}
    </header>
  );
}
