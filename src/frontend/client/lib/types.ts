// Kontrakt API klienta (src/client_api/handler.py, onboarding.py)

export type OnboardingOption = { id: string; label: string; icon: string | null; short: string };

export type OnboardingField = {
  id: string;
  type: "single" | "multi" | "select";
  label?: string;
  required: boolean;
  maxSelect?: number;
  options: OnboardingOption[];
};

export type OnboardingStep = { id: string; icon: string; title: string; hint: string; fields: OnboardingField[] };

export type Onboarding = { version: string; steps: OnboardingStep[] };

// { idPola: [idOpcji, ...] }
export type Answers = Record<string, string[]>;

export type Preferences = {
  interests: string[];
  themes: string[];
  formats: string[];
  audience: string[];
  occasion: string[];
  activityLevel: string[];
  cost: string[];
  mode: string[];
  setting: string[];
  registration: string[];
  accessibility: string[];
  days: string[];
  timeOfDay: string[];
  weekend: boolean;
  district: string | null;
  travelRange: string | null;
  maxPrice: number | null;
  ageRange: string | null;
};

export type Me = {
  userId: string;
  email: string | null;
  name: string | null;
  picture: string | null;
  identityProvider: string;
  needsOnboarding: boolean;
  onboardingOutdated: boolean;
  profile: { answers: Answers; completedAt: string; preferences: Preferences; ragProfile: string } | null;
};

// --- rekomendacje (src/recommender_api/handler.py, present.py) ---

// "date" = wybrany dzień (?date=RRRR-MM-DD); "week" obsługuje API, strona go nie pokazuje
export type When = "today" | "tomorrow" | "weekend" | "week" | "date";

// Najbliższy termin w wybranym oknie: konkretne wydarzenie albo zajęcia co tydzień
export type Slot =
  | { recurring?: undefined; start: string; end: string | null; allDay: boolean }
  | { recurring: true; date: string | null; day: string | null; start: string | null; end: string | null };

export type Recommendation = {
  id: string;
  title: string;
  lead: string;
  url: string | null;
  ticketUrl: string | null;
  imageUrl: string | null;
  origin: "um_warszawa" | "partner";
  source: string;
  kind: "event" | "recurring";
  partnerName: string | null;
  district: string | null;
  venue: { name?: string | null; address?: string | null } | null;
  location: { lat: number; lon: number } | null;
  online: boolean;
  slot: Slot | null;
  schedule: { day: string; start?: string | null; end?: string | null }[];
  price: { min: number | null; max: number | null; currency: string } | null;
  tags: {
    theme?: string[];
    format?: string[];
    audience?: string[];
    cost?: string;
    mode?: string;
    setting?: string;
    registration?: string;
    activity_level?: string;
  };
  reason: string;
  reasonSource: "llm" | "rules";
  score: number;
};

export type Recommendations = {
  generatedAt: string;
  when: When;
  window: { from: string; to: string };
  query: string | null;
  district: string | null;
  area: "local" | "nearby" | "city";
  areaRelaxed: boolean;
  ranking: "llm" | "cosine";
  cached: boolean; // z zapisanego zestawu (tabela recommendations), bez ponownego liczenia
  updating: boolean; // w tle liczy się nowsza wersja (AI układa kolejność albo odświeżenie po 12 h)
  items: Recommendation[];
  index: { builtAt: string | null; events: number | null };
};

// 202: zestaw właśnie się liczy (np. zaraz po zmianie profilu) - zapytać ponownie za retryAfter s
export type Preparing = { status: "preparing"; retryAfter: number };
