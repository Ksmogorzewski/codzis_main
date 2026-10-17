import { createFileRoute } from "@tanstack/react-router";
import { CrewChatScreen } from "@/components/crew/crew-chat-screen";
import { GenericRouteError } from "@/components/layout/route-error";

// Czat ekipy wybranego wydarzenia (wejście ze szczegółów, sekcja „Ekipa na to wydarzenie”; tylko dla
// zapisanych). `$id_`: osobny ekran, nie zagnieżdżony w szczegółach. Wydarzenie jak w wydarzenie.$id.tsx,
// członkowie z listy zapisanych; wiadomości na razie DEMO (lib/crew-demo.ts).
export const Route = createFileRoute("/_app/wydarzenie/$id_/ekipa")({
  component: CrewChatScreen,
  errorComponent: GenericRouteError,
});
