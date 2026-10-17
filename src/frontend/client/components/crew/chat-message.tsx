import { Icon } from "@/components/ui/icon";
import { AI_HOST, type ChatMessage as Message } from "@/lib/crew-chat";
import { cn } from "@/lib/utils";

const enter = "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-200";
const bubble = "flex max-w-[82%] flex-col gap-1 px-4 py-3 text-base leading-snug text-pretty wrap-anywhere";
const author = "text-[13px] font-bold";

export function ChatMessage({ message }: { message: Message }) {
  switch (message.kind) {
    case "me":
      return (
        <div className={cn(bubble, enter, "self-end rounded-[20px_20px_6px_20px] bg-primary text-primary-foreground")}>
          <span className={cn(author, "text-primary-foreground/80")}>{message.author}</span>
          {message.text}
        </div>
      );
    case "them":
      return (
        <div className={cn(bubble, enter, "self-start rounded-[20px_20px_20px_6px] border bg-card")}>
          <span className={cn(author, "text-muted-foreground")}>{message.author}</span>
          {message.text}
        </div>
      );
    case "ai":
      return (
        <div className={cn(enter, "flex flex-col gap-2 rounded-2xl border border-primary-soft bg-primary-soft px-4 py-3 leading-snug")}>
          <div className="flex items-center gap-2 text-meta font-bold text-primary-ink">
            <Icon name="record_voice_over" size={22} />
            {AI_HOST} WarsawNow
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

/** „Marta pisze…” — symulacja pisania przed wiadomością ze scenariusza demo. */
export function TypingIndicator({ who }: { who: string }) {
  return (
    <div
      className={cn(enter, "flex items-center gap-2 self-start rounded-full border bg-card px-4 py-2.5 text-meta text-muted-foreground")}
    >
      <span aria-hidden="true" className="flex gap-1">
        <span className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-bounce" />
        <span className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-bounce motion-safe:[animation-delay:150ms]" />
        <span className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-bounce motion-safe:[animation-delay:300ms]" />
      </span>
      {who} pisze…
    </div>
  );
}
