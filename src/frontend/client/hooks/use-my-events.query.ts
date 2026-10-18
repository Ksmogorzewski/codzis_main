import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { myEventsKey } from "@/lib/query-keys";
import { MyEventsSchema } from "@/lib/schemas";

// GET /api/me/events: wydarzenia, na które jestem zapisany (zakładka „Twoje”, plakietka nieprzeczytanych
// w nawigacji): najpierw nadchodzące od najbliższego terminu, potem minione (past), maks. 100.
export const myEventsQueryOptions = queryOptions({
  queryKey: myEventsKey(),
  queryFn: async ({ signal }) => unwrap(await apiGet("/api/me/events", MyEventsSchema, signal)),
});

export const useMyEvents = () => useQuery(myEventsQueryOptions);
