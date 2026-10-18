import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/ui/icon";
import { settingInfo } from "@/lib/events";
import type { Card } from "@/lib/schemas";
import { mainTag } from "@/lib/tags";

/**
 * Naklejki na plakacie: główny temat (tags.theme[0]), od organizatora, pod dachem / plener (tags.setting), online.
 * Kafelek na listach (`setting={false}`) pokazuje sam temat - pod dachem / plener jest w szczegółach.
 */
export function EventBadges({ card, large, setting: withSetting = true }: { card: Card; large?: boolean; setting?: boolean }) {
  const setting = withSetting ? settingInfo(card.tags.setting) : null;
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
