import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet, unwrap } from "@/lib/api";
import { attendeesKey } from "@/lib/query-keys";
import { AttendeesSchema } from "@/lib/schemas";

// GET /api/events/{id}/attendees: liczba i imiona zapisanych (najnowsi najpierw, maks. 100).
export const attendeesQueryOptions = (id: string) =>
  queryOptions({
    queryKey: attendeesKey(id),
    queryFn: async ({ signal }) =>
      unwrap(await apiGet(`/api/events/${encodeURIComponent(id)}/attendees`, AttendeesSchema, signal)),
  });

export const useAttendees = (id: string) => useQuery(attendeesQueryOptions(id));
