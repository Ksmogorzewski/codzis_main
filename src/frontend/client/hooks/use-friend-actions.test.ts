import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { friendsGoingKey, friendsKey } from "@/lib/query-keys";
import { ok } from "@/lib/result";
import type { FriendsOverview } from "@/lib/schemas";
import { acceptFriendOptions, removeFriendOptions } from "./use-friend-actions.mutation";

const overview: FriendsOverview = {
  code: "WAW-7K2P9X",
  friends: [
    { userId: "u1", name: "Ola", since: null },
    { userId: "u2", name: "Kuba", since: null },
  ],
  incoming: [{ userId: "u3", name: "Zosia", createdAt: null }],
  outgoing: [],
};

function setup() {
  const qc = new QueryClient();
  qc.setQueryData(friendsKey(), overview);
  qc.setQueryData(friendsGoingKey(), { items: [], byEvent: { e1: [{ userId: "u2", name: "Ola" }] } });
  return qc;
}

describe("remove friend invalidates going", () => {
  it("usunięcie: znajomy znika od razu, a „friends” i „friends-going” są unieważnione", async () => {
    const qc = setup();
    const calls: string[] = [];
    const observer = new MutationObserver(
      qc,
      removeFriendOptions(qc, async (id) => {
        calls.push(id);
        return ok({});
      }),
    );
    await observer.mutate("u1");
    expect(calls).toEqual(["u1"]);
    expect(qc.getQueryData<FriendsOverview>(friendsKey())?.friends.map((f) => f.userId)).toEqual(["u2"]);
    expect(qc.getQueryState(friendsKey())?.isInvalidated).toBe(true);
    expect(qc.getQueryState(friendsGoingKey())?.isInvalidated).toBe(true);
  });

  it("błąd: lista wraca do stanu sprzed usunięcia", async () => {
    const qc = setup();
    const observer = new MutationObserver(
      qc,
      removeFriendOptions(qc, async () => ({
        data: null,
        error: { status: 503, code: "http_503", message: "x", fields: [] },
      })),
    );
    await observer.mutate("u1").catch(() => {});
    expect(qc.getQueryData<FriendsOverview>(friendsKey())?.friends.map((f) => f.userId)).toEqual(["u1", "u2"]);
  });
});

describe("409 bez kodu (wyścig transakcji)", () => {
  it("nie jest traktowany jak „uzupełnij profil”", async () => {
    const qc = setup();
    const observer = new MutationObserver(
      qc,
      acceptFriendOptions(qc, async () => ({
        data: null,
        error: { status: 409, code: "needs_onboarding", message: "Stan zaproszenia zmienił się, odśwież listę", fields: [] },
      })),
    );
    const error = await observer.mutate("u3").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 409, code: "friends_conflict" });
  });
});

describe("akceptacja zaproszenia", () => {
  it("unieważnia znajomych i „znajomi idą”", async () => {
    const qc = setup();
    const observer = new MutationObserver(qc, acceptFriendOptions(qc, async () => ok({ status: "friends" })));
    await observer.mutate("u3");
    expect(qc.getQueryState(friendsKey())?.isInvalidated).toBe(true);
    expect(qc.getQueryState(friendsGoingKey())?.isInvalidated).toBe(true);
  });
});
