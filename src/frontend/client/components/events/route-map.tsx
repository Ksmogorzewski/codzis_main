import { Icon } from "@/components/ui/icon";

type Props = {
  /** Adres Maps Embed API z lib/maps.ts (trasa komunikacją albo sama pinezka). */
  src: string;
  eventTitle: string;
  /** Skąd liczona jest trasa, np. „Trasa komunikacją miejską z Twojej lokalizacji”. */
  caption: string;
};

/** Dojazd w szczegółach wydarzenia: osadzona mapa Google (mockup: mapa w karcie z faktami). */
export function RouteMap({ src, eventTitle, caption }: Props) {
  return (
    <section aria-label="Dojazd" className="flex flex-col border-t">
      <iframe
        key={src}
        src={src}
        title={`Mapa dojazdu: ${eventTitle}`}
        loading="lazy"
        // Google sprawdza domenę strony przy kluczu ograniczonym do referrerów
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
        className="block h-56 w-full border-0 bg-secondary md:h-64"
      />
      <p className="flex items-center gap-1.5 px-4 py-3 text-sm text-muted-foreground">
        <Icon name="directions_transit" size={18} />
        {caption}
      </p>
    </section>
  );
}
