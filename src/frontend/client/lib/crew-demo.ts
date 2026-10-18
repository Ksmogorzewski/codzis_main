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

type Line = (members: readonly string[]) => ChatMessageInput;
const them =
  (i: number, text: string): Line =>
  (members) => ({ kind: "them", author: pick(members, i), text });

// Warianty rozmowy startowej - wydarzenie dostaje zawsze ten sam (variantOf), różne wydarzenia różne.
const SEEDS: Line[][] = [
  [
    them(0, "Cześć wszystkim! Też jesteście pierwszy raz na czymś takim?"),
    them(1, "Hej! Dla mnie to drugi raz, ale pierwszy w grupie."),
    them(2, "Siema, u mnie totalny debiut. Mam nadzieję, że nie będzie padać."),
  ],
  [
    them(0, "Hej! Ktoś już był na czymś podobnym?"),
    them(1, "Ja nie, dlatego fajnie, że idziemy w grupie."),
  ],
  [
    them(0, "Dzień dobry ekipo! Cieszę się, że ktoś jeszcze się wybiera."),
    them(2, "Cześć! Ja dołączam, ale mogę być kilka minut później."),
    them(1, "Spoko, poczekamy przy wejściu."),
  ],
];

// Wiadomości, które „przychodzą” później (symulacja na zakładce „Twoje”, lib/crew-inbox.ts) - bez
// zmyślonych miejsc i godzin.
const LATE: Line[] = [
  them(1, "Ktoś już wie, jak najlepiej dojechać?"),
  them(0, "Będę trochę wcześniej, dam znać, jak dotrę."),
  them(2, "Nie mogę się doczekać, do zobaczenia!"),
];
export const DEMO_LATE_MAX = LATE.length;

/** Stały numer wariantu dla wydarzenia (0..n-1): to samo id zawsze daje tę samą rozmowę. */
export function variantOf(eventId: string, n: number): number {
  let hash = 0;
  for (const ch of eventId) hash = (hash * 31 + ch.charCodeAt(0)) % 10007;
  return hash % n;
}

/** Wiadomości, które już są w czacie, zanim dołączę; bez id wydarzenia - pierwszy wariant. */
export const demoSeed = (members: readonly string[], eventId?: string): ChatMessageInput[] =>
  SEEDS[eventId === undefined ? 0 : variantOf(eventId, SEEDS.length)].map((line) => line(members));

/**
 * Cała dotychczasowa rozmowa wydarzenia: start + `arrived` wiadomości, które „przyszły” później
 * (kolejność zależna od wydarzenia, maks. DEMO_LATE_MAX). Ta sama lista na „Twoje” i w czacie.
 */
export function demoInbox(members: readonly string[], eventId: string, arrived: number): ChatMessageInput[] {
  const start = variantOf(eventId, LATE.length);
  const late = Array.from({ length: Math.min(Math.max(0, arrived), LATE.length) }, (_, i) =>
    LATE[(start + i) % LATE.length](members),
  );
  return [...demoSeed(members, eventId), ...late];
}

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
