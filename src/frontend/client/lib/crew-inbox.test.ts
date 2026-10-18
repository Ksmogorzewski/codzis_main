import { afterEach, describe, expect, it, vi } from "vitest";
import {
  arrivalTarget,
  createInboxStore,
  type Inbox,
  markRead,
  messageCount,
  scheduleDemoArrival,
  totalUnread,
  unreadCount,
  unreadLabel,
  withArrival,
} from "./crew-inbox";
import { DEMO_LATE_MAX, demoInbox, demoSeed } from "./crew-demo";

describe("nieprzeczytane (czyste funkcje)", () => {
  it("nowo zapisane wydarzenie: cała rozmowa startowa ekipy jest nieprzeczytana", () => {
    expect(unreadCount({}, "kal-1")).toBe(demoSeed([], "kal-1").length);
    expect(unreadCount({}, "kal-1")).toBeGreaterThan(0);
  });

  it("otwarcie czatu oznacza wszystko jako przeczytane", () => {
    const inbox = markRead({}, "kal-1");
    expect(unreadCount(inbox, "kal-1")).toBe(0);
    expect(markRead(inbox, "kal-1")).toBe(inbox); // bez zmian = ten sam obiekt (bez zbędnych odświeżeń)
  });

  it("nowa wiadomość po przeczytaniu: jedna nieprzeczytana, aż do limitu scenariusza", () => {
    let inbox: Inbox = markRead({}, "kal-1");
    inbox = withArrival(inbox, "kal-1") ?? inbox;
    expect(unreadCount(inbox, "kal-1")).toBe(1);
    expect(messageCount(inbox, "kal-1")).toBe(demoInbox([], "kal-1", 1).length);
    for (let i = 1; i < DEMO_LATE_MAX; i++) inbox = withArrival(inbox, "kal-1") ?? inbox;
    expect(withArrival(inbox, "kal-1")).toBeNull();
  });

  it("suma dla nawigacji i cel symulacji: pierwsze wydarzenie, w którym jeszcze coś może przyjść", () => {
    let inbox: Inbox = markRead(markRead({}, "a"), "b");
    expect(totalUnread(inbox, ["a", "b"])).toBe(0);
    expect(arrivalTarget(inbox, ["a", "b"])).toBe("a");
    for (let i = 0; i < DEMO_LATE_MAX; i++) inbox = withArrival(inbox, "a") ?? inbox;
    expect(arrivalTarget(inbox, ["a", "b"])).toBe("b");
    expect(totalUnread(inbox, ["a", "b"])).toBe(DEMO_LATE_MAX);
    expect(arrivalTarget(inbox, [])).toBeNull();
  });

  it("zepsuty stan (np. ręcznie zmieniony storage) nie daje ujemnych liczb", () => {
    expect(unreadCount({ x: { read: 99, arrived: 0 } }, "x")).toBe(0);
  });

  it("podpis plakietki po polsku", () => {
    expect(unreadLabel(1)).toBe("1 nowa wiadomość");
    expect(unreadLabel(3)).toBe("3 nowe wiadomości");
    expect(unreadLabel(5)).toBe("5 nowych wiadomości");
  });
});

describe("magazyn przeczytanych", () => {
  const memoryStorage = () => {
    let saved: unknown = null;
    return { read: () => saved, write: (v: Inbox) => (saved = structuredClone(v)), saved: () => saved };
  };

  it("zapisuje i odczytuje stan; powiadamia subskrybentów", () => {
    const storage = memoryStorage();
    const store = createInboxStore(storage);
    const listener = vi.fn();
    store.subscribe(listener);
    store.markRead("kal-1");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(createInboxStore(storage).get()).toEqual(store.get()); // po przeładowaniu ten sam stan
  });

  it("bez dostępu do storage działa w pamięci", () => {
    const store = createInboxStore({
      read: () => {
        throw new Error("SecurityError");
      },
      write: () => {
        throw new Error("QuotaExceededError");
      },
    });
    expect(store.get()).toEqual({});
    store.markRead("kal-1");
    expect(unreadCount(store.get(), "kal-1")).toBe(0);
  });

  it("niepoprawna zawartość storage = pusty stan", () => {
    const store = createInboxStore({ read: () => ({ a: { read: "x" } }), write: () => {} });
    expect(store.get()).toEqual({});
  });
});

describe("DEMO: symulowana nowa wiadomość", () => {
  afterEach(() => vi.useRealTimers());

  it("po czasie raz na sesję strony; anulowanie przed czasem nic nie zmienia", () => {
    vi.useFakeTimers();
    const store = createInboxStore({ read: () => null, write: () => {} });
    store.markRead("a");
    const arrived = vi.fn();

    const cancel = scheduleDemoArrival(store, ["a"], arrived, 1000);
    vi.advanceTimersByTime(500);
    cancel();
    vi.advanceTimersByTime(1000);
    expect(arrived).not.toHaveBeenCalled();

    scheduleDemoArrival(store, ["a"], arrived, 1000);
    vi.advanceTimersByTime(1000);
    expect(arrived).toHaveBeenCalledWith("a");
    expect(unreadCount(store.get(), "a")).toBe(1);

    scheduleDemoArrival(store, ["a"], arrived, 1000);
    vi.advanceTimersByTime(5000);
    expect(arrived).toHaveBeenCalledTimes(1);
  });

  it("bez zapisanych wydarzeń nic się nie dzieje", () => {
    vi.useFakeTimers();
    const store = createInboxStore({ read: () => null, write: () => {} });
    const arrived = vi.fn();
    scheduleDemoArrival(store, [], arrived, 10);
    vi.advanceTimersByTime(100);
    expect(arrived).not.toHaveBeenCalled();
  });
});
