import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/ui/icon";
import { settingInfo } from "@/lib/events";
import type { Card } from "@/lib/schemas";

/** Plakietki na zdjęciu: od organizatora, pod dachem / plener (tags.setting), online. */
export function EventBadges({ card, large }: { card: Card; large?: boolean }) {
  const setting = settingInfo(card.tags.setting);
  const size = large ? "lg" : "default";
  const icon = large ? 18 : 16;
  return (
    <>
      {card.origin === "partner" && (
        <Badge variant="brand" size={size}>
          Od organizatora
        </Badge>
      )}
      {setting && (
        <Badge variant="surface" size={size} className="pl-2">
          <Icon name={setting.icon} size={icon} />
          {setting.label}
        </Badge>
      )}
      {card.online && (
        <Badge variant="surface" size={size} className="pl-2">
          <Icon name="devices" size={icon} />
          Online
        </Badge>
      )}
    </>
  );
}
