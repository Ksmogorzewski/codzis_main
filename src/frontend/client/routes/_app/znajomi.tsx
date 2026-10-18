import { createFileRoute } from "@tanstack/react-router";
import { FriendsRouteError, FriendsSkeleton, FriendsView } from "@/components/friends/friends-view";
import { friendsQueryOptions } from "@/hooks/use-friends.query";
import { friendsGoingQueryOptions } from "@/hooks/use-friends-going.query";

// Znajomi (GET /api/friends + GET /api/friends/going): wydarzenia znajomych, zaproszenia, mój kod i QR.
export const Route = createFileRoute("/_app/znajomi")({
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(friendsGoingQueryOptions);
    return context.queryClient.ensureQueryData(friendsQueryOptions);
  },
  pendingComponent: FriendsSkeleton,
  errorComponent: FriendsRouteError,
  component: FriendsView,
});
