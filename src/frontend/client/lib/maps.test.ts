import { describe, expect, it } from "vitest";
import { destinationOf, districtOf, mapsEmbedUrl, originOf } from "./maps";

const params = (url: string | null) => Object.fromEntries(new URL(url ?? "about:blank").searchParams);

describe("maps: osadzona mapa z trasą", () => {
  it("cel: współrzędne wydarzenia, bez nich miejsce + Warszawa; online i bez miejsca: brak", () => {
    expect(destinationOf({ online: false, location: { lat: 52.2297, lon: 21.0122 }, venue: null })).toBe("52.2297,21.0122");
    expect(destinationOf({ online: false, location: null, venue: { name: "Hala Koło", address: "Obozowa 60" } })).toBe(
      "Hala Koło, Obozowa 60, Warszawa",
    );
    expect(destinationOf({ online: true, location: { lat: 52.2, lon: 21 }, venue: null })).toBeNull();
    expect(destinationOf({ online: false, location: null, venue: { name: null, address: null } })).toBeNull();
  });

  it("start: pozycja z przeglądarki (5 miejsc po przecinku), inaczej dzielnica z profilu", () => {
    expect(originOf({ lat: 52.229712345, lon: 21.012228765 }, "Wola")).toBe("52.22971,21.01223");
    expect(originOf(null, "Wola")).toBe("Wola, Warszawa");
    expect(originOf(null, null)).toBeNull();
  });

  it("dzielnica z preferencji profilu tylko jako tekst", () => {
    expect(districtOf({ district: "Mokotów" })).toBe("Mokotów");
    expect(districtOf({ district: 5 })).toBeNull();
    expect(districtOf({ district: "  " })).toBeNull();
    expect(districtOf(null)).toBeNull();
  });

  it("trasa komunikacją miejską: tryb directions, transit, po polsku", () => {
    const url = mapsEmbedUrl({ key: "k1", origin: "Wola, Warszawa", destination: "52.2297,21.0122" });
    expect(url?.startsWith("https://www.google.com/maps/embed/v1/directions?")).toBe(true);
    expect(params(url)).toEqual({
      key: "k1",
      origin: "Wola, Warszawa",
      destination: "52.2297,21.0122",
      mode: "transit",
      language: "pl",
      region: "PL",
    });
  });

  it("bez punktu startu: sama pinezka (tryb place)", () => {
    const url = mapsEmbedUrl({ key: "k1", origin: null, destination: "Hala Koło, Obozowa 60, Warszawa" });
    expect(url?.startsWith("https://www.google.com/maps/embed/v1/place?")).toBe(true);
    expect(params(url)).toEqual({ key: "k1", q: "Hala Koło, Obozowa 60, Warszawa", language: "pl", region: "PL" });
  });

  it("bez klucza albo bez celu: brak mapy (zostaje link do Map Google)", () => {
    expect(mapsEmbedUrl({ key: "", origin: "Wola, Warszawa", destination: "52.2,21" })).toBeNull();
    expect(mapsEmbedUrl({ key: undefined, origin: null, destination: "52.2,21" })).toBeNull();
    expect(mapsEmbedUrl({ key: "k1", origin: "Wola, Warszawa", destination: null })).toBeNull();
  });
});
