import { createFileRoute } from "@tanstack/react-router";
import { DataRouteError } from "@/components/layout/route-error";
import { MyEventsSkeleton, MyEventsView } from "@/components/my-events/my-events-view";
import { myEventsQueryOptions } from "@/hooks/use-my-events.query";

// Twoje wydarzenia (GET /api/me/events): moje zapisy z czatami ekip (GET /api/me/crews, components/crew/crew-chat-row.tsx).
export const Route = createFileRoute("/_app/twoje")({
  loader: ({ context }) => context.queryClient.ensureQueryData(myEventsQueryOptions),
  pendingComponent: MyEventsSkeleton,
  errorComponent: DataRouteError,
  component: MyEventsView,
});
