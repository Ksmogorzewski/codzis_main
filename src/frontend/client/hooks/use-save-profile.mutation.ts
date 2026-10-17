import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPut, unwrap } from "@/lib/api";
import { meKey, recommendationsRootKey } from "@/lib/query-keys";
import { type Answers, MeSchema } from "@/lib/schemas";

// PUT /api/profile {answers} -> Me. Nowy profil = nowe rekomendacje, więc stare usuwamy z cache.
export function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (answers: Answers) => unwrap(await apiPut("/api/profile", { answers }, MeSchema)),
    onSuccess: (me) => {
      queryClient.setQueryData(meKey(), me);
      queryClient.removeQueries({ queryKey: recommendationsRootKey() });
    },
  });
}
