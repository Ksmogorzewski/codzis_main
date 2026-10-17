// Stan czatu mikro-ekipy (mockup_czatu_warsawnow_2): czat zablokowany do pierwszej odpowiedzi na lodołamacz,
// potem wiadomości ekipy i Wodzireja AI; przycisk „Pokaż Kartę Koloru” po ustaleniu punktu zbiórki.

export type ChatMessageInput =
  | { kind: "me"; text: string }
  | { kind: "them"; author: string; text: string }
  /** Wodzirej AI: podsumowanie ekipy z punktem i godziną zbiórki. */
  | { kind: "ai"; text: string; meetingPoint: string; time: string };

export type ChatMessage = ChatMessageInput & { id: string };

export type ChatState = {
  locked: boolean;
  messages: ChatMessage[];
  /** Widoczny przycisk karty koloru. */
  beacon: boolean;
};

export type ChatAction =
  | { type: "send"; text: string }
  | { type: "receive"; message: ChatMessageInput; beacon?: boolean };

const withId = (messages: ChatMessage[], m: ChatMessageInput): ChatMessage[] => [
  ...messages,
  { ...m, id: `m${messages.length + 1}` },
];

export function initialChat(seed: ChatMessageInput[]): ChatState {
  return { locked: true, beacon: false, messages: seed.reduce(withId, []) };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "send": {
      const text = action.text.trim();
      if (!text) return state;
      return { ...state, locked: false, messages: withId(state.messages, { kind: "me", text }) };
    }
    case "receive":
      return {
        ...state,
        beacon: state.beacon || action.beacon === true,
        messages: withId(state.messages, action.message),
      };
  }
}
