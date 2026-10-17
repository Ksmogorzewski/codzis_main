// Stan czatu mikro-ekipy (mockup_czatu_warsawnow_2): czat zablokowany do pierwszej odpowiedzi na lodołamacz,
// potem wiadomości ekipy i Wodzireja AI; przycisk „Pokaż Kartę Koloru” po ustaleniu punktu zbiórki.
// Czyste funkcje: reducer, harmonogram odpowiedzi („X pisze…”), skład ekipy z listy zapisanych.
import { attendeeLabel } from "./community";

export const AI_HOST = "Wodzirej AI";

export type ChatMessageInput =
  | { kind: "me"; author: string; text: string }
  | { kind: "them"; author: string; text: string }
  /** Wodzirej AI: podsumowanie ekipy z punktem i godziną zbiórki. */
  | { kind: "ai"; text: string; meetingPoint: string; time: string };

export type ChatMessage = ChatMessageInput & { id: string };

export type ChatState = {
  locked: boolean;
  messages: ChatMessage[];
  /** Kto teraz „pisze” (symulacja); null = nikt. */
  typing: string | null;
  /** Widoczny przycisk karty koloru. */
  beacon: boolean;
};

export type ChatAction =
  | { type: "send"; text: string; author: string }
  | { type: "typing"; author: string }
  | { type: "receive"; message: ChatMessageInput; beacon?: boolean };

const withId = (messages: ChatMessage[], m: ChatMessageInput): ChatMessage[] => [
  ...messages,
  { ...m, id: `m${messages.length + 1}` },
];

export function initialChat(seed: ChatMessageInput[]): ChatState {
  return { locked: true, typing: null, beacon: false, messages: seed.reduce(withId, []) };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "send": {
      const text = action.text.trim();
      if (!text) return state;
      return { ...state, locked: false, messages: withId(state.messages, { kind: "me", author: action.author, text }) };
    }
    case "typing":
      return { ...state, typing: action.author };
    case "receive":
      return {
        ...state,
        typing: null,
        beacon: state.beacon || action.beacon === true,
        messages: withId(state.messages, action.message),
      };
  }
}

/** Krok scenariusza odpowiedzi; afterMs liczone od poprzedniego kroku. */
export type ScriptStep = { afterMs: number; message: ChatMessageInput; beacon?: boolean };
export type TimedAction = { at: number; action: ChatAction };

/** Kto „pisze” daną wiadomość. */
export const authorOf = (m: ChatMessageInput): string => (m.kind === "ai" ? AI_HOST : m.author);

/**
 * Scenariusz -> akcje w czasie (ms od odblokowania czatu): „X pisze…” przez typingMs przed każdą
 * wiadomością (krócej, gdy krok jest krótszy), potem sama wiadomość.
 */
export function timeline(script: ScriptStep[], typingMs = 1000): TimedAction[] {
  let at = 0;
  return script.flatMap(({ afterMs, message, beacon }) => {
    const typingAt = at + Math.max(0, afterMs - typingMs);
    at += afterMs;
    return [
      { at: typingAt, action: { type: "typing", author: authorOf(message) } },
      { at, action: { type: "receive", message, beacon } },
    ];
  });
}

type Person = { name: string | null; isMe: boolean };

/**
 * Pozostali członkowie ekipy (bez mnie): najpierw imiona prawdziwych zapisanych (bez pustych i bez
 * powtórzeń), brakujące miejsca uzupełniamy imionami z demo, aż będzie `size` osób.
 */
export function crewMembers(people: readonly Person[] | undefined, fallback: readonly string[], size: number): string[] {
  const real = (people ?? []).flatMap((p) => {
    const name = p.name?.trim();
    return !p.isMe && name && name !== "Ktoś" ? [name] : [];
  });
  const unique = [...new Set(real)];
  const extra = fallback.filter((n) => !unique.includes(n));
  return [...unique, ...extra].slice(0, Math.max(0, size));
}

/** Podpis moich wiadomości: imię z ID tokenu z dopiskiem „(Ty)”, bez imienia samo „Ty”. */
export const ownLabel = (name: string | null): string => attendeeLabel({ name, isMe: true });

/** „Ty, Piotr, Kamil i Antek” — skład ekipy w jednej linii (ja zawsze pierwszy). */
export function membersLine(others: readonly string[]): string {
  const all = ["Ty", ...others];
  return all.length === 1 ? "Ty" : `${all.slice(0, -1).join(", ")} i ${all.at(-1)}`;
}
