// Ankieta po zmianie pytań: wymuszamy ją tylko kontu, które nigdy jej nie wypełniło (needsOnboarding).
// Gdy doszło wymagane pytanie (onboardingOutdated), „Dla Ciebie” pokazuje tylko baner z prośbą o uzupełnienie,
// który po „Później” znika dla tej wersji pytań (GET /api/onboarding -> version) - nowa wersja pokaże go znowu.
import { readJson, writeJson } from "./storage";

type OnboardingState = { needsOnboarding: boolean; onboardingOutdated: boolean };

/** Dokąd przekierować przed ekranem głównym: do ankiety tylko konto bez wypełnionej ankiety, inaczej null. */
export const onboardingRedirect = (me: OnboardingState): "/profil" | null => (me.needsOnboarding ? "/profil" : null);

/** Baner „Mamy nowe pytania”: profil wypełniony, doszło wymagane pytanie, a ta wersja pytań nie została ukryta. */
export function showNewQuestions(
  me: OnboardingState | undefined,
  version: string | undefined,
  dismissed: ReadonlySet<string>,
): boolean {
  if (!me || !version || me.needsOnboarding || !me.onboardingOutdated) return false;
  return !dismissed.has(version);
}

export const dismissKey = (version: string) => `warsawnow.new-questions-dismissed.${version}`;

type DismissStore = { read: (key: string) => unknown; write: (key: string, value: true) => void };

const localDismiss: DismissStore = {
  read: (key) => readJson<unknown>("local", key),
  write: (key, value) => writeJson("local", key, value),
};

/** Czy baner tej wersji pytań został ukryty („Później”); bez dostępu do storage - nie. */
export function isDismissed(version: string, store: DismissStore = localDismiss): boolean {
  try {
    return store.read(dismissKey(version)) === true;
  } catch {
    return false;
  }
}

/** Zapamiętuje ukrycie banera dla tej wersji pytań; błąd storage nie przeszkadza (baner znika do przeładowania). */
export function dismissNewQuestions(version: string, store: DismissStore = localDismiss): void {
  try {
    store.write(dismissKey(version), true);
  } catch {
    // brak dostępu do storage - baner wróci po przeładowaniu strony
  }
}
