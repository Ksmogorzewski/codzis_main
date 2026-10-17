import type { ChatMessageInput, ScriptStep } from "./crew-chat";

// DEMO: czat ekipy to na razie symulacja (mockup_czatu_warsawnow_2) — backendu ekip ani wiadomości nie ma.
// Prawdziwe są tylko: wydarzenie (tytuł, kategoria, miejsce, termin), imiona zapisanych (GET
// /api/events/{id}/attendees) i moje imię z ID tokenu. Teksty wiadomości, lodołamacz i odpowiedzi są
// przykładowe. Po dodaniu API (np. GET /api/events/{id}/crew) ten plik zastąpi schemat w lib/schemas.ts
// i hook w hooks/.

export const DEMO_CREW = {
  /** Wielkość ekipy razem ze mną. */
  capacity: 4,
  /** Imiona na wolne miejsca, gdy prawdziwych zapisanych jest mniej. */
  names: ["Kamil", "Marta", "Antek"],
  icebreaker: "Jaka jest Twoja ulubiona ulica lub budynek w Warszawie?",
};

/** Imię członka ekipy z listy; poza zakresem - imię z demo. */
const pick = (members: readonly string[], i: number) => members[i] ?? DEMO_CREW.names[i] ?? "Ktoś";

/** Wiadomości, które już są w czacie, zanim dołączę (pierwsze trzy osoby ekipy). */
export const demoSeed = (members: readonly string[]): ChatMessageInput[] => [
  { kind: "them", author: pick(members, 0), text: "Cześć wszystkim! Też jesteście pierwszy raz na czymś takim?" },
  { kind: "them", author: pick(members, 1), text: "Hej! Dla mnie to drugi raz, ale pierwszy w grupie." },
  { kind: "them", author: pick(members, 2), text: "Siema, u mnie totalny debiut. Mam nadzieję, że nie będzie padać." },
];

type ScriptInput = {
  members: readonly string[];
  category: string;
  /** Miejsce z wydarzenia (placeLabel); null = nieznane. */
  place: string | null;
  /** Termin z wydarzenia (slotLabel); null = nieznany. */
  when: string | null;
};

/**
 * Odpowiedzi po odblokowaniu czatu (moja odpowiedź na lodołamacz). Punkt i czas zbiórki tylko z danych
 * wydarzenia - bez zmyślonych miejsc i godzin.
 */
export function demoScript({ members, category, place, when }: ScriptInput): ScriptStep[] {
  return [
    {
      afterMs: 1800,
      message: { kind: "them", author: pick(members, 1), text: "Dobra odpowiedź! Miło Cię poznać." },
    },
    {
      afterMs: 2200,
      message: {
        kind: "ai",
        text: `Mamy komplet ${DEMO_CREW.capacity} osób! Łączy Was kategoria „${category}”.`,
        meetingPoint: place ? `Punkt zbiórki: przy wejściu, ${place}` : "Punkt zbiórki: przy wejściu na miejsce wydarzenia",
        time: when ? `${when} · zbiórka 15 minut wcześniej` : "Zbiórka 15 minut przed startem",
      },
    },
    {
      afterMs: 2000,
      message: { kind: "them", author: pick(members, 0), text: "Świetnie, dla mnie pasuje. Będę przy wejściu!" },
      beacon: true,
    },
  ];
}
