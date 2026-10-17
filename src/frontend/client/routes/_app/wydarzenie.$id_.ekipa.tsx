import { createFileRoute } from "@tanstack/react-router";
import { CrewChatScreen } from "@/components/crew/crew-chat-screen";
import { GenericRouteError } from "@/components/layout/route-error";

// Czat ekipy wybranego wydarzenia (wejście ze szczegółów). `$id_`: osobny ekran, nie zagnieżdżony w szczegółach.
// Karta wydarzenia z cache rekomendacji jak w wydarzenie.$id.tsx; wiadomości na razie demo (lib/crew-demo.ts).
export const Route = createFileRoute("/_app/wydarzenie/$id_/ekipa")({
  component: CrewChatScreen,
  errorComponent: GenericRouteError,
});
