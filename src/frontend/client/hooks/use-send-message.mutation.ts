import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost, unwrap } from "@/lib/api";
import { markCrewRead, withMessage } from "@/lib/crew-chat";
import { crewKey, myCrewsKey } from "@/lib/query-keys";
import { type Crew, type MyCrews, SentMessageSchema } from "@/lib/schemas";

// POST /api/events/{id}/crew/messages {text} -> {message}: zapisana wiadomość od razu trafia do czatu
// (bez czekania na odpytywanie; to samo id z odpytywania nie zdubluje jej - mergeCrew) i do podglądu
// ostatniej wiadomości na „Twoje”. Błędy (np. 429 „Wysyłasz za szybko”) pokazuje okno czatu.
export function useSendMessage(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (text: string) =>
      unwrap(await apiPost(`/api/events/${encodeURIComponent(id)}/crew/messages`, { text }, SentMessageSchema)),
    onSuccess: ({ message }) => {
      const crew = queryClient.setQueryData<Crew>(crewKey(id), (c) => (c ? withMessage(c, message) : c));
      if (crew) queryClient.setQueryData<MyCrews>(myCrewsKey(), (mine) => markCrewRead(mine, id, crew));
    },
  });
}
