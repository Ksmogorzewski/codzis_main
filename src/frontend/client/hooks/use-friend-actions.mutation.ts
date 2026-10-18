import { mutationOptions, type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorText } from "@/components/layout/route-error";
import { type ApiResult, apiDelete, apiPost, apiPut, isNameRequired, NEEDS_ONBOARDING, unwrap } from "@/lib/api";
import { friendsGoingKey, friendsKey } from "@/lib/query-keys";
import {
  EmptySchema,
  FriendCodeSchema,
  type FriendsOverview,
  FriendStatusSchema,
  type InviteResult,
  InviteResultSchema,
} from "@/lib/schemas";

// Akcje znajomych: zaproszenie kodem, akceptacja/odrzucenie, usunięcie, nowy kod. Po każdej mutacji
// unieważniamy „friends”; gdy zmienia się lista znajomych - też „friends-going” (linijki „Ola idzie”
// znikają z kart bez odświeżania strony). 409 name_required obsługuje globalny onError (prośba o imię).

const path = (p: string, id: string) => `${p}/${encodeURIComponent(id)}`;

/**
 * Wynik albo wyjątek. 409 bez kodu (rzadki wyścig transakcji: „Stan zaproszenia zmienił się…”) toApiError
 * oznacza jako needs_onboarding - tu to nie ankieta, więc zmieniamy kod, żeby globalny onError nie wysłał na /profil.
 */
function unwrapFriends<T>(r: ApiResult<T>): T {
  if (r.error?.code === NEEDS_ONBOARDING) return unwrap<T>({ data: null, error: { ...r.error, code: "friends_conflict" } });
  return unwrap(r);
}

function refresh(qc: QueryClient, going: boolean) {
  void qc.invalidateQueries({ queryKey: friendsKey() });
  if (going) void qc.invalidateQueries({ queryKey: friendsGoingKey() });
}

/** Toast z komunikatem serwera (po polsku); prośbę o imię pokazuje już globalny onError. */
function showError(error: unknown, fallback: string) {
  if (!isNameRequired(error)) toast.error(errorText(error, fallback));
}

/** Optymistyczna zmiana listy znajomych/zaproszeń; zwraca poprzedni stan do przywrócenia przy błędzie. */
async function patchOverview(qc: QueryClient, patch: (o: FriendsOverview) => FriendsOverview) {
  await qc.cancelQueries({ queryKey: friendsKey() });
  const previous = qc.getQueryData<FriendsOverview>(friendsKey());
  if (previous) qc.setQueryData(friendsKey(), patch(previous));
  return { previous };
}

const restore = (qc: QueryClient, ctx: { previous?: FriendsOverview } | undefined) => {
  if (ctx?.previous) qc.setQueryData(friendsKey(), ctx.previous);
};

type Call<T> = (id: string) => Promise<ApiResult<T>>;

// --- usunięcie znajomego: DELETE /api/friends/{userId} ---

export const removeFriendOptions = (
  qc: QueryClient,
  call: Call<unknown> = (id) => apiDelete(path("/api/friends", id), EmptySchema),
) =>
  mutationOptions({
    mutationFn: async (userId: string) => unwrapFriends(await call(userId)),
    onMutate: (userId) =>
      patchOverview(qc, (o) => ({ ...o, friends: o.friends.filter((f) => f.userId !== userId) })),
    onError: (error, _id, ctx) => {
      restore(qc, ctx);
      showError(error, "Nie udało się usunąć znajomego.");
    },
    onSettled: () => refresh(qc, true),
  });

export function useRemoveFriend() {
  const qc = useQueryClient();
  return useMutation(removeFriendOptions(qc));
}

// --- akceptacja zaproszenia: PUT /api/friends/requests/{userId} ---

export const acceptFriendOptions = (
  qc: QueryClient,
  call: Call<unknown> = (id) => apiPut(path("/api/friends/requests", id), undefined, FriendStatusSchema),
) =>
  mutationOptions({
    mutationFn: async (userId: string) => unwrapFriends(await call(userId)),
    onError: (error) => showError(error, "Nie udało się przyjąć zaproszenia."),
    onSuccess: () => toast("Jesteście znajomymi"),
    onSettled: () => refresh(qc, true),
  });

export function useAcceptFriend() {
  const qc = useQueryClient();
  return useMutation(acceptFriendOptions(qc));
}

// --- odrzucenie zaproszenia (ciche dla zapraszającego): DELETE /api/friends/requests/{userId} ---

export function useDeclineFriend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => unwrapFriends(await apiDelete(path("/api/friends/requests", userId), EmptySchema)),
    onMutate: (userId) =>
      patchOverview(qc, (o) => ({ ...o, incoming: o.incoming.filter((r) => r.userId !== userId) })),
    onError: (error, _id, ctx) => {
      restore(qc, ctx);
      showError(error, "Nie udało się odrzucić zaproszenia.");
    },
    onSettled: () => refresh(qc, false),
  });
}

// --- zaproszenie kodem: POST /api/friends/invite {code} ---

export function useInviteFriend() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (code: string): Promise<InviteResult> =>
      unwrapFriends(await apiPost("/api/friends/invite", { code }, InviteResultSchema)),
    onError: (error) => showError(error, "Nie udało się wysłać zaproszenia."),
    onSuccess: (r) => toast(r.status === "friends" ? "Jesteście znajomymi" : "Zaproszenie wysłane"),
    // automatyczna akceptacja (status "friends") zmienia też „znajomi idą”
    onSettled: (r) => refresh(qc, r?.status === "friends"),
  });
}

// --- nowy kod (stary przestaje działać, znajomi zostają): POST /api/friends/code ---

export function useRegenerateCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrapFriends(await apiPost("/api/friends/code", undefined, FriendCodeSchema)),
    onError: (error) => showError(error, "Nie udało się utworzyć nowego kodu."),
    onSuccess: ({ code }) => {
      qc.setQueryData<FriendsOverview>(friendsKey(), (o) => o && { ...o, code });
      toast("Nowy kod gotowy. Stary już nie działa.");
    },
  });
}
