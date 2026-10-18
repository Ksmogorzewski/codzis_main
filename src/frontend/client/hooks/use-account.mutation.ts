import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AccountInput } from "@/lib/account";
import { apiPut, unwrap } from "@/lib/api";
import { meKey, recommendationsRootKey } from "@/lib/query-keys";
import { MeSchema } from "@/lib/schemas";

// PUT /api/me {birthDate} -> Me (dane konta; imię i odpowiedzi ankiety bez zmian). Z daty urodzenia backend
// liczy przedział wieku w preferencjach, więc - jak po zapisie ankiety - stare rekomendacje usuwamy z cache.
export function useSaveAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: AccountInput) => unwrap(await apiPut("/api/me", input, MeSchema)),
    onSuccess: (me) => {
      queryClient.setQueryData(meKey(), me);
      queryClient.removeQueries({ queryKey: recommendationsRootKey() });
    },
  });
}
