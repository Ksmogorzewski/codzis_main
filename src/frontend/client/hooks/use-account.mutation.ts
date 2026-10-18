import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AccountInput } from "@/lib/account";
import { apiPut, unwrap } from "@/lib/api";
import { meKey } from "@/lib/query-keys";
import { MeSchema } from "@/lib/schemas";

// PUT /api/me {lastName, birthDate} -> Me (dane konta; imię i odpowiedzi ankiety bez zmian)
export function useSaveAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: AccountInput) => unwrap(await apiPut("/api/me", input, MeSchema)),
    onSuccess: (me) => queryClient.setQueryData(meKey(), me),
  });
}
