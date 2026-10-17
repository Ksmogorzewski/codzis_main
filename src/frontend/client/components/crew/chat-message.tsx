import { Icon } from "@/components/ui/icon";
import type { ChatMessage as Message } from "@/lib/crew-chat";
import { cn } from "@/lib/utils";

const enter = "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-200";
const bubble = "max-w-[82%] px-4 py-3 text-base leading-snug text-pretty wrap-anywhere";

export function ChatMessage({ message }: { message: Message }) {
  switch (message.kind) {
    case "me":
      return (
        <div className={cn(bubble, enter, "self-end rounded-[20px_20px_6px_20px] bg-primary text-primary-foreground")}>
          {message.text}
        </div>
      );
    case "them":
      return (
        <div className={cn(bubble, enter, "self-start rounded-[20px_20px_20px_6px] border bg-card")}>
          <span className="mb-1 block text-[13px] font-bold text-muted-foreground">{message.author}</span>
          {message.text}
        </div>
      );
    case "ai":
      return (
        <div className={cn(enter, "flex flex-col gap-2 rounded-lg bg-primary-soft px-4 py-3 leading-snug")}>
          <div className="flex items-center gap-2 text-meta font-bold text-primary-ink">
            <Icon name="record_voice_over" size={22} />
            Wodzirej AI WarsawNow
          </div>
          <p className="text-pretty">{message.text}</p>
          <div className="flex flex-col gap-1 text-meta font-semibold">
            <span className="flex gap-1.5">
              <Icon name="location_on" size={18} className="text-primary-ink" />
              {message.meetingPoint}
            </span>
            <span className="flex gap-1.5">
              <Icon name="schedule" size={18} className="text-primary-ink" />
              {message.time}
            </span>
          </div>
        </div>
      );
  }
}
