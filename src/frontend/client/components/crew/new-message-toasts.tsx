import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { Icon } from "@/components/ui/icon";
import { useMyCrews } from "@/hooks/use-my-crews.query";
import { arrivals, messagePreview } from "@/lib/crew-chat";
import type { MyCrews } from "@/lib/schemas";

/**
 * Toast „Nowa wiadomość w czacie: <tytuł>” z „Otwórz”, gdy przy odpytywaniu plakietek (GET /api/me/crews, co 30 s)
 * przybyło cudzych wiadomości. Na ekranie tego czatu bez toastu (otwarty czat sam oznacza wszystko jako
 * przeczytane). Bez powiadomień przeglądarki. Montowany raz, w układzie zalogowanych (routes/_app.tsx).
 */
export function NewMessageToasts() {
  const mine = useMyCrews();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const seen = useRef<MyCrews | undefined>(undefined);

  useEffect(() => {
    const next = mine.data;
    if (!next) return;
    for (const crew of arrivals(seen.current, next)) {
      if (!crew.last || pathname === `/wydarzenie/${crew.eventId}/ekipa`) continue;
      toast(`Nowa wiadomość w czacie: ${crew.title || "Twoja ekipa"}`, {
        id: `crew-${crew.eventId}`,
        icon: <Icon name="forum" />,
        description: messagePreview(crew.last),
        duration: 8000,
        action: {
          label: "Otwórz",
          onClick: () => void navigate({ to: "/wydarzenie/$id/ekipa", params: { id: crew.eventId } }),
        },
      });
    }
    seen.current = next;
  }, [mine.data, navigate, pathname]);

  return null;
}
