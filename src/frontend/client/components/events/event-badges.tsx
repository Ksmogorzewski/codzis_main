import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/ui/icon";
import { settingInfo } from "@/lib/events";
import type { Card } from "@/lib/schemas";
import { mainTag } from "@/lib/tags";

/** Naklejki na plakacie: główny temat (tags.theme[0]), od organizatora, pod dachem / plener (tags.setting), online. */
export function EventBadges({ card, large }: { card: Card; large?: boolean }) {
  const setting = settingInfo(card.tags.setting);
  const main = mainTag(card.tags);
  const size = large ? "lg" : "default";
  const icon = large ? 18 : 16;
  const sticker = "tracking-[0.06em] uppercase";
  return (
    <>
      {main && (
        <Badge variant="surface" size={size} className={sticker}>
          {main}
        </Badge>
      )}
      {card.origin === "partner" && (
        <Badge variant="surface" size={size} className={sticker}>
          Od organizatora
        </Badge>
      )}
      {setting && (
        <Badge variant="surface" size={size} className={`${sticker} pl-1.5`}>
          <Icon name={setting.icon} size={icon} />
          {setting.label}
        </Badge>
      )}
      {card.online && (
        <Badge variant="surface" size={size} className={`${sticker} pl-1.5`}>
          <Icon name="devices" size={icon} />
          Online
        </Badge>
      )}
    </>
  );
}
