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
