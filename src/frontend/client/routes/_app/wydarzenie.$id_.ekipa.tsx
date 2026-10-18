import { createFileRoute } from "@tanstack/react-router";
import { CrewChatScreen } from "@/components/crew/crew-chat-screen";
import { GenericRouteError } from "@/components/layout/route-error";

// Czat ekipy wybranego wydarzenia (wejście ze szczegółów, sekcja „Ekipa na to wydarzenie”; tylko dla
// zapisanych). `$id_`: osobny ekran, nie zagnieżdżony w szczegółach. Wydarzenie jak w wydarzenie.$id.tsx,
// ekipa i wiadomości z GET /api/events/{id}/crew (hooks/use-crew.query.ts, bez loadera - pierwsze zapytanie
// dołącza do ekipy, więc nie może iść z podglądu linku).
export const Route = createFileRoute("/_app/wydarzenie/$id_/ekipa")({
  component: CrewChatScreen,
  errorComponent: GenericRouteError,
});
