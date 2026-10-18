import { createFileRoute } from "@tanstack/react-router";
import { AddFriendView } from "@/components/friends/add-friend-view";
import { GenericRouteError } from "@/components/layout/route-error";

// Link z QR: #/znajomi/dodaj/WAW-XXXXXX (poza układem /znajomi - „_” w nazwie). Bez sesji strażnik w _app.tsx
// prowadzi przez /login?redirect=… i po zalogowaniu wraca tutaj.
export const Route = createFileRoute("/_app/znajomi_/dodaj/$code")({
  component: AddFriendView,
  errorComponent: GenericRouteError,
});
