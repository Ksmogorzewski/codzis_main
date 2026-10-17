import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { onboardingKey } from "@/lib/query-keys";
import { OnboardingSchema } from "@/lib/schemas";

// GET /api/onboarding: kroki ankiety (zmieniają się tylko z nową wersją backendu).
export const onboardingQueryOptions = queryOptions({
  queryKey: onboardingKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/onboarding", OnboardingSchema, signal)),
  staleTime: 10 * 60_000,
});

export const useOnboarding = () => useQuery(onboardingQueryOptions);
