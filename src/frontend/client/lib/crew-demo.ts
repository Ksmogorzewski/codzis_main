import type { ChatMessageInput } from "./crew-chat";

// DEMO: treść z mockupu czatu (mockup_czatu_warsawnow_2). Backendu ekip jeszcze nie ma — po dodaniu API
// (np. GET /api/events/<id>/crew) ten plik zastąpi schemat w lib/schemas.ts i hook w hooks/.
// Nazwę ekipy i kategorię bierzemy z wybranego wydarzenia; reszta to przykład.

export const DEMO_CREW = {
  members: 4,
  capacity: 4,
  icebreaker: "Jaka jest Twoja ulubiona ulica lub budynek w Warszawie?",
};

export const DEMO_SEED: ChatMessageInput[] = [
  { kind: "them", author: "Kamil", text: "Cześć wszystkim! Też jesteście pierwszy raz na takim spacerze?" },
  { kind: "them", author: "Marta", text: "Hej! Ja byłam rok temu na Woli, ale Śródmieścia nocą jeszcze nie zwiedzałam." },
  { kind: "them", author: "Antek", text: "Siema, ja totalny debiut. Mam nadzieję, że nie będzie padać." },
];

/** Odpowiedzi po odblokowaniu czatu; afterMs liczone od poprzedniego kroku. */
export const demoScript = (category: string): { afterMs: number; message: ChatMessageInput; beacon?: boolean }[] => [
  {
    afterMs: 1500,
    message: {
      kind: "ai",
      text: `Mamy komplet 4 osób! Łączy Was kategoria „${category}”.`,
      meetingPoint: "Punkt zbiórki: stacja Veturilo przed wejściem",
      time: "18:45 (za 20 minut)",
    },
  },
  {
    afterMs: 1000,
    message: { kind: "them", author: "Kamil", text: "Świetnie, dla mnie pasuje. Będę pod rowerami!" },
    beacon: true,
  },
];
