import { Icon } from "@/components/ui/icon";
import { useFriendsOn } from "@/hooks/use-friends-going.query";
import { friendsLine } from "@/lib/friends";
import { cn } from "@/lib/utils";

/** „Ola idzie” / „Kuba i Ola idą” na karcie: znajomi zapisani na wydarzenie (bez znajomych - nic). */
export function FriendsLine({ eventId, className }: { eventId: string; className?: string }) {
  const text = friendsLine(useFriendsOn(eventId));
  if (!text) return null;
  return (
    <span className={cn("flex gap-1.5 font-semibold text-primary-ink", className)}>
      <Icon name="diversity_3" size={18} filled />
      {text}
    </span>
  );
}
