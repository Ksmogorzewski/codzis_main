import { describe, expect, it } from "vitest";
import { distanceKm, distanceLabel, walkLabel, walkMinutes } from "./geo";

const PKiN = { lat: 52.2318, lon: 21.0060 };
const ZAMEK = { lat: 52.2479, lon: 21.0153 };

describe("geo", () => {
  it("odległość po łuku (haversine)", () => {
    expect(distanceKm(PKiN, PKiN)).toBe(0);
    expect(distanceKm(PKiN, ZAMEK)).toBeCloseTo(1.89, 1);
  });

  it("czas pieszo: 5 km/h, w górę, co najmniej 1 min", () => {
    expect(walkMinutes(1)).toBe(12);
    expect(walkMinutes(0.01)).toBe(1);
    expect(walkMinutes(2.05)).toBe(25);
  });

  it("etykieta odległości: metry poniżej 1 km, km z przecinkiem", () => {
    expect(distanceLabel(0.35)).toBe("350 m");
    expect(distanceLabel(0.004)).toBe("10 m");
    expect(distanceLabel(1.26)).toBe("1,3 km");
    expect(distanceLabel(12)).toBe("12 km");
  });

  it("odległość i czas pieszo tylko przy obu pozycjach; daleko bez czasu pieszo", () => {
    expect(walkLabel(PKiN, ZAMEK)).toBe("1,9 km · ok. 23 min pieszo");
    expect(walkLabel(null, ZAMEK)).toBeNull();
    expect(walkLabel(PKiN, null)).toBeNull();
    expect(walkLabel(PKiN, { lat: 52.4, lon: 21.0 })).toBe("19 km");
  });
});
