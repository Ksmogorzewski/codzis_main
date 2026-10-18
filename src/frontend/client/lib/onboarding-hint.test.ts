import { describe, expect, it } from "vitest";
import { dismissKey, dismissNewQuestions, isDismissed, onboardingRedirect, showNewQuestions } from "./onboarding-hint";

const fresh = { needsOnboarding: true, onboardingOutdated: false };
const outdated = { needsOnboarding: false, onboardingOutdated: true };
const current = { needsOnboarding: false, onboardingOutdated: false };

function memoryStore() {
  const data = new Map<string, unknown>();
  return { data, read: (key: string) => data.get(key), write: (key: string, value: true) => void data.set(key, value) };
}

const broken = {
  read: (): unknown => {
    throw new Error("SecurityError");
  },
  write: () => {
    throw new Error("QuotaExceededError");
  },
};

describe("przekierowanie do ankiety przed ekranem głównym", () => {
  it("tylko konto bez wypełnionej ankiety idzie do /profil", () => {
    expect(onboardingRedirect(fresh)).toBe("/profil");
    expect(onboardingRedirect(outdated)).toBeNull();
    expect(onboardingRedirect(current)).toBeNull();
  });
});

describe("baner o nowych pytaniach", () => {
  it("pokazuje się przy nieaktualnym profilu i nieukrytej wersji", () => {
    expect(showNewQuestions(outdated, "abc123", new Set())).toBe(true);
    expect(showNewQuestions(outdated, "abc123", new Set(["stara"]))).toBe(true);
  });

  it("nie pokazuje się po ukryciu tej wersji, bez wersji ani bez profilu", () => {
    expect(showNewQuestions(outdated, "abc123", new Set(["abc123"]))).toBe(false);
    expect(showNewQuestions(outdated, undefined, new Set())).toBe(false);
    expect(showNewQuestions(undefined, "abc123", new Set())).toBe(false);
  });

  it("nie pokazuje się przy aktualnym profilu ani przed pierwszą ankietą", () => {
    expect(showNewQuestions(current, "abc123", new Set())).toBe(false);
    expect(showNewQuestions({ ...fresh, onboardingOutdated: true }, "abc123", new Set())).toBe(false);
  });
});

describe("ukrycie banera (localStorage)", () => {
  it("zapamiętuje ukrycie per wersja pytań", () => {
    const store = memoryStore();
    expect(isDismissed("v1", store)).toBe(false);
    dismissNewQuestions("v1", store);
    expect(isDismissed("v1", store)).toBe(true);
    expect(isDismissed("v2", store)).toBe(false);
    expect([...store.data.keys()]).toEqual([dismissKey("v1")]);
    expect(dismissKey("v1")).toContain("v1");
  });

  it("błąd storage nie rzuca: baner traktujemy jako nieukryty", () => {
    expect(() => dismissNewQuestions("v1", broken)).not.toThrow();
    expect(isDismissed("v1", broken)).toBe(false);
  });

  it("inna wartość pod kluczem nie liczy się jako ukrycie", () => {
    const store = memoryStore();
    store.data.set(dismissKey("v1"), "tak");
    expect(isDismissed("v1", store)).toBe(false);
  });
});
