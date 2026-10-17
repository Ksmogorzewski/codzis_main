// Osadzona mapa Google z trasą do wydarzenia (Maps Embed API) w szczegółach wydarzenia.
// Punkt startu: pozycja z przeglądarki, gdy użytkownik się zgodzi, inaczej dzielnica z profilu.
// Pozycja trafia wyłącznie do osadzonej mapy Google – nie do naszego API.
import type { Point } from "./geo";
import type { Card } from "./schemas";

const EMBED_URL = "https://www.google.com/maps/embed/v1";

/** Cel trasy: współrzędne wydarzenia, bez nich nazwa i adres miejsca + Warszawa; online i bez miejsca: null. */
export function destinationOf(card: Pick<Card, "online" | "location" | "venue">): string | null {
  if (card.online) return null;
  if (card.location) return `${card.location.lat},${card.location.lon}`;
  const place = [card.venue?.name, card.venue?.address].filter(Boolean).join(", ");
  return place ? `${place}, Warszawa` : null;
}

/** Start trasy: pozycja z przeglądarki (5 miejsc po przecinku, ~1 m), inaczej dzielnica; null, gdy brak obu. */
export function originOf(position: Point | null, district: string | null): string | null {
  if (position) return `${position.lat.toFixed(5)},${position.lon.toFixed(5)}`;
  return district ? `${district}, Warszawa` : null;
}

/** Dzielnica z preferencji profilu (preferences.district z ankiety), tylko niepusty tekst. */
export function districtOf(preferences: Record<string, unknown> | null | undefined): string | null {
  const district = preferences?.district;
  return typeof district === "string" && district.trim() ? district.trim() : null;
}

type EmbedInput = { key: string | null | undefined; origin: string | null; destination: string | null };

/**
 * Adres iframe Maps Embed API: trasa komunikacją miejską (directions, mode=transit), a bez punktu
 * startu sama pinezka (place). null bez klucza albo celu – wtedy zostaje link do Map Google.
 */
export function mapsEmbedUrl({ key, origin, destination }: EmbedInput): string | null {
  if (!key || !destination) return null;
  const params = new URLSearchParams({ key });
  if (origin) {
    params.set("origin", origin);
    params.set("destination", destination);
    params.set("mode", "transit");
  } else {
    params.set("q", destination);
  }
  params.set("language", "pl");
  params.set("region", "PL");
  return `${EMBED_URL}/${origin ? "directions" : "place"}?${params}`;
}
