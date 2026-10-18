import { describe, expect, it } from "vitest";
import { friendsLine, inviteLink, nearestFor, normalizeCode, qrPath } from "./friends";
import { AttendeesSchema, FriendsGoingSchema, FriendsOverviewSchema, InviteResultSchema } from "./schemas";

describe("normalizeCode (te same reguły co backend)", () => {
  it("kod wpisany „byle jak” działa jak poprawny", () => {
    expect(normalizeCode("waw 7k2p9x")).toBe("WAW-7K2P9X");
    expect(normalizeCode("7K2P9X")).toBe("WAW-7K2P9X");
    expect(normalizeCode(" WAW-7K2P9X ")).toBe("WAW-7K2P9X");
    expect(normalizeCode("waw-7k2-p9x")).toBe("WAW-7K2P9X");
  });

  it("zła długość albo znaki spoza alfabetu (0/O/1/I) - null", () => {
    expect(normalizeCode("WAW-7K2")).toBeNull();
    expect(normalizeCode("WAW-0OIL00")).toBeNull();
    expect(normalizeCode("WAW-7K2P9X1")).toBeNull();
    expect(normalizeCode("")).toBeNull();
    expect(normalizeCode("WAW-7K2P9!")).toBeNull();
  });
});

describe("inviteLink", () => {
  it("link do ekranu zaproszenia na hashu", () => {
    expect(inviteLink("WAW-7K2P9X", "https://portal.waw-out.pl", "/")).toBe(
      "https://portal.waw-out.pl/#/znajomi/dodaj/WAW-7K2P9X",
    );
  });

  it("ścieżka strony zostaje (np. index.html)", () => {
    expect(inviteLink("WAW-7K2P9X", "http://localhost:8000", "/index.html")).toBe(
      "http://localhost:8000/index.html#/znajomi/dodaj/WAW-7K2P9X",
    );
  });
});

describe("friendsLine", () => {
  it("nikt - null", () => {
    expect(friendsLine([])).toBeNull();
  });

  it("jedna osoba", () => {
    expect(friendsLine(["Ola"])).toBe("Ola idzie");
  });

  it("dwie osoby", () => {
    expect(friendsLine(["Kuba", "Ola"])).toBe("Kuba i Ola idą");
    expect(friendsLine(["Ola", "Kuba"])).toBe("Kuba i Ola idą");
  });

  it("trzy i więcej: pierwsze imię alfabetycznie i liczba reszty", () => {
    expect(friendsLine(["Ola", "Kuba", "Zosia"])).toBe("Kuba i 2 innych znajomych idzie");
    expect(friendsLine(["Ola", "Łucja", "Ania", "Kuba"])).toBe("Ania i 3 innych znajomych idzie");
  });
});

describe("nearestFor", () => {
  const items = [
    { id: "a", friends: ["Kuba"] },
    { id: "b", friends: ["Kuba", "Ola"] },
  ];

  it("pierwsza (najbliższa) karta z imieniem znajomego", () => {
    expect(nearestFor("Ola", items)?.id).toBe("b");
    expect(nearestFor("Kuba", items)?.id).toBe("a");
  });

  it("bez zapisów - null", () => {
    expect(nearestFor("Zosia", items)).toBeNull();
  });
});

describe("qrPath", () => {
  it("ciemne moduły jako kwadraty 1x1 w ścieżce SVG", () => {
    expect(
      qrPath([
        [true, false],
        [false, true],
      ]),
    ).toBe("M0 0h1v1h-1zM1 1h1v1h-1z");
  });

  it("pusta macierz - pusta ścieżka", () => {
    expect(qrPath([])).toBe("");
  });
});

describe("schematy znajomych (kontrakt client-api)", () => {
  it("GET /api/friends: brakujące listy puste", () => {
    const data = FriendsOverviewSchema.parse({ code: "WAW-7K2P9X", friends: [{ userId: "u1", name: "Ola", since: 1 }] });
    expect(data).toMatchObject({ code: "WAW-7K2P9X", incoming: [], outgoing: [] });
    expect(data.friends[0]).toMatchObject({ userId: "u1", name: "Ola" });
  });

  it("GET /api/friends/going: karty z imionami i mapa wydarzenie -> imiona", () => {
    const data = FriendsGoingSchema.parse({
      items: [{ id: "e1", title: "Koncert", friends: ["Kuba", "Ola"] }, { id: 7 }],
      byEvent: { e1: ["Kuba", "Ola"], e2: "zepsute" },
    });
    expect(data.items.map((c) => [c.id, c.friends])).toEqual([["e1", ["Kuba", "Ola"]]]);
    expect(data.byEvent).toEqual({ e1: ["Kuba", "Ola"] });
    expect(FriendsGoingSchema.parse({})).toEqual({ items: [], byEvent: {} });
  });

  it("POST /api/friends/invite: status", () => {
    expect(InviteResultSchema.parse({ status: "friends", userId: "u1", name: "Ola" }).status).toBe("friends");
    expect(InviteResultSchema.parse({ status: "pending" }).status).toBe("pending");
  });

  it("lista zapisanych: isFriend domyślnie false", () => {
    const data = AttendeesSchema.parse({ people: [{ name: "Ola", isFriend: true }, { name: "Ktoś" }] });
    expect(data.people.map((p) => p.isFriend)).toEqual([true, false]);
  });
});
