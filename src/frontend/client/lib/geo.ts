// Odległość i czas pieszo liczone w przeglądarce. Pozycja użytkownika nie trafia do API.
export type Point = { lat: number; lon: number };

const EARTH_KM = 6371;
const WALK_KMH = 5;
const MAX_WALK_KM = 5; // dalej "ok. 70 min pieszo" nikomu nie pomaga – sama odległość

const rad = (deg: number) => (deg * Math.PI) / 180;

/** Odległość po łuku (haversine) w km. */
export function distanceKm(a: Point, b: Point): number {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Minuty pieszo przy 5 km/h, zaokrąglone w górę, co najmniej 1. */
export const walkMinutes = (km: number) => Math.max(1, Math.ceil((km / WALK_KMH) * 60));

/** "350 m" / "1,3 km" / "12 km". */
export function distanceLabel(km: number): string {
  if (km < 1) return `${Math.max(10, Math.round((km * 1000) / 10) * 10)} m`;
  if (km < 10) return `${(Math.round(km * 10) / 10).toString().replace(".", ",")} km`;
  return `${Math.round(km)} km`;
}

/** "1,9 km · ok. 23 min pieszo"; null, gdy nie znamy którejś pozycji. */
export function walkLabel(from: Point | null, to: Point | null): string | null {
  if (!from || !to) return null;
  const km = distanceKm(from, to);
  const dist = distanceLabel(km);
  return km > MAX_WALK_KM ? dist : `${dist} · ok. ${walkMinutes(km)} min pieszo`;
}
