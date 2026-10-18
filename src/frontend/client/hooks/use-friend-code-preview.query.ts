import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { friendCodeKey } from "@/lib/query-keys";
import { FriendPreviewSchema } from "@/lib/schemas";

// GET /api/friends/code/{code} -> {userId, name}: czyj to kod (ekran zaproszenia). Zły kod liczy się
// do limitu prób (10 na godzinę), więc bez ponowień i bez odświeżania w tle.
export const friendCodePreviewQueryOptions = (code: string) =>
  queryOptions({
    queryKey: friendCodeKey(code),
    queryFn: async ({ signal }) =>
      unwrap(await apiGet(`/api/friends/code/${encodeURIComponent(code)}`, FriendPreviewSchema, signal)),
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });

export const useFriendCodePreview = (code: string | null) =>
  useQuery({ ...friendCodePreviewQueryOptions(code ?? ""), enabled: code !== null });
