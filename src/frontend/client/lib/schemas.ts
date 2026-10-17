// Odpowiedzi API portalu klienta sprawdzane Zodem (kontrakt: src/client_api/handler.py, onboarding.py,
// src/recommender_api/handler.py, present.py). Tolerancyjnie: brakujące pola opcjonalne dostają
// wartości domyślne, więc typy wyjściowe są pełne, a drobna zmiana po stronie API nie wywraca ekranu.
import { z } from "zod";

const nullableString = z.string().nullable().default(null);
const stringList = z.array(z.string()).default([]);

// --- ankieta: GET /api/onboarding ---

export const OnboardingOptionSchema = z.object({
  id: z.string(),
  label: z.string(),
  icon: nullableString,
  short: z.string(),
});

export const OnboardingFieldSchema = z.object({
  id: z.string(),
  type: z.enum(["single", "multi", "select"]),
  label: z.string().optional(),
  required: z.boolean().default(false),
  maxSelect: z.number().int().positive().optional(),
  options: z.array(OnboardingOptionSchema),
});

export const OnboardingStepSchema = z.object({
  id: z.string(),
  icon: z.string(),
  title: z.string(),
  hint: z.string().default(""),
  fields: z.array(OnboardingFieldSchema),
});

export const OnboardingSchema = z.object({
  version: z.string(),
  steps: z.array(OnboardingStepSchema),
});

export type OnboardingOption = z.infer<typeof OnboardingOptionSchema>;
export type OnboardingField = z.infer<typeof OnboardingFieldSchema>;
export type OnboardingStep = z.infer<typeof OnboardingStepSchema>;
export type Onboarding = z.infer<typeof OnboardingSchema>;

// { idPola: [idOpcji, ...] } - body PUT /api/profile to { answers }
export const AnswersSchema = z.record(z.string(), z.array(z.string()));
export type Answers = z.infer<typeof AnswersSchema>;

// --- profil: GET /api/me, odpowiedź PUT /api/profile ---

// Preferencje liczy backend z odpowiedzi; front ich nie potrzebuje do działania, więc luźno.
export const PreferencesSchema = z.record(z.string(), z.unknown());

export const MeSchema = z.object({
  userId: z.string(),
  email: nullableString,
  name: nullableString,
  picture: nullableString,
  identityProvider: nullableString,
  needsOnboarding: z.boolean(),
  onboardingOutdated: z.boolean().default(false),
  profile: z
    .object({
      answers: AnswersSchema.default({}),
      completedAt: nullableString,
      preferences: PreferencesSchema.nullable().default(null),
      ragProfile: nullableString,
    })
    .nullable()
    .default(null),
});

export type Me = z.infer<typeof MeSchema>;

// --- rekomendacje: GET /api/recommendations?when=&date=&q=&limit= ---

// "date" = wybrany dzień (parametr date=RRRR-MM-DD, do 60 dni naprzód)
export const WHEN_VALUES = ["today", "tomorrow", "weekend", "week", "date"] as const;
export const WhenSchema = z.enum(WHEN_VALUES);
export type When = z.infer<typeof WhenSchema>;

// Najbliższy termin w wybranym oknie: zajęcia co tydzień albo konkretne wydarzenie
const RecurringSlotSchema = z.object({
  recurring: z.literal(true),
  date: nullableString,
  day: nullableString,
  start: nullableString,
  end: nullableString,
});
const DatedSlotSchema = z.object({
  recurring: z.undefined().optional(),
  start: z.string(),
  end: nullableString,
  allDay: z.boolean().default(false),
});
export const SlotSchema = z.union([RecurringSlotSchema, DatedSlotSchema]);
export type Slot = z.infer<typeof SlotSchema>;

// Współrzędne bywają stringami (API UM); z pustego stringa nie robimy 0.
const coordinate = z.preprocess((v) => (typeof v === "string" && v.trim() !== "" ? Number(v) : v), z.number().finite());
const LocationSchema = z.object({ lat: coordinate, lon: coordinate });

export const CardSchema = z.object({
  id: z.string(),
  title: z.string(),
  lead: z.string().default(""),
  url: nullableString,
  ticketUrl: nullableString,
  imageUrl: nullableString,
  origin: z.string().default("um_warszawa"), // "um_warszawa" | "partner"
  source: z.string().default(""),
  kind: z.string().default("event"), // "event" | "recurring"
  partnerName: nullableString,
  district: nullableString,
  venue: z
    .object({ name: z.string().nullish(), address: z.string().nullish() })
    .nullable()
    .default(null),
  location: LocationSchema.nullable().default(null),
  online: z.boolean().default(false),
  slot: SlotSchema.nullable().default(null),
  schedule: z
    .array(z.object({ day: z.string(), start: z.string().nullish(), end: z.string().nullish() }))
    .default([]),
  price: z
    .object({ min: z.number().nullable().default(null), max: z.number().nullable().default(null), currency: z.string().default("PLN") })
    .nullable()
    .default(null),
  tags: z
    .object({
      theme: z.array(z.string()).optional(),
      format: z.array(z.string()).optional(),
      audience: z.array(z.string()).optional(),
      cost: z.string().optional(),
      mode: z.string().optional(),
      setting: z.string().optional(),
      registration: z.string().optional(),
      activity_level: z.string().optional(),
    })
    .default({}),
  reason: z.string().default(""),
  reasonSource: z.string().default("rules"), // "llm" | "rules"
  score: z.number().default(0),
});

export type Card = z.infer<typeof CardSchema>;
/** Dawna nazwa z types.ts (lib/events.ts). */
export type Recommendation = Card;

export const RecommendationsSchema = z.object({
  generatedAt: z.string(),
  when: WhenSchema,
  window: z.object({ from: z.string(), to: z.string() }).nullable().default(null),
  query: nullableString,
  district: nullableString,
  area: z.enum(["local", "nearby", "city"]).default("city"),
  areaRelaxed: z.boolean().default(false),
  ranking: z.string().default("cosine"), // "llm" | "cosine"
  // Zepsutą kartę pomijamy, zamiast odrzucać całą odpowiedź.
  items: z.array(z.unknown()).transform((xs) =>
    xs.flatMap((x) => {
      const r = CardSchema.safeParse(x);
      return r.success ? [r.data] : [];
    }),
  ),
  index: z
    .object({ builtAt: nullableString, events: z.number().nullable().default(null) })
    .default({ builtAt: null, events: null }),
  // Zestaw z zapisu (tabela recommendations); updating = w tle liczy się nowsza wersja
  // (AI układa kolejność albo odświeżenie po 12 h) - warto zapytać ponownie za chwilę.
  cached: z.boolean().default(false),
  updating: z.boolean().default(false),
});

export type Recommendations = z.infer<typeof RecommendationsSchema>;

// 202: zestawu jeszcze nie ma (albo zmienił się profil) i właśnie się liczy - zapytać za retryAfter s.
export const PreparingSchema = z.object({
  status: z.literal("preparing"),
  retryAfter: z.number().positive().default(2),
});
export type Preparing = z.infer<typeof PreparingSchema>;

export const RecommendationsResponseSchema = z.union([PreparingSchema, RecommendationsSchema]);

// --- błąd API: {error: "komunikat PL", fields?, code?} ---

export const ApiErrorBodySchema = z.object({
  error: z.string(),
  fields: stringList,
  code: z.string().optional(),
});
