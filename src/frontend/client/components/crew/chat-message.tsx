import { Icon } from "@/components/ui/icon";
import { authorLabel, HOST, hostCard, type MeetingInfo, messageTime, noticeText } from "@/lib/crew-chat";
import type { Crew, CrewMessage } from "@/lib/schemas";
import { cn } from "@/lib/utils";

const enter = "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 motion-safe:duration-200";
const bubble = "flex max-w-[82%] flex-col gap-1 px-4 py-3 text-base leading-snug text-pretty wrap-anywhere";
const mineBubble = "self-end bg-primary text-primary-foreground";
const author = "text-[13px] font-bold";

type Props = { message: CrewMessage; crew: Pick<Crew, "capacity" | "icebreaker">; info: MeetingInfo; now: Date };

/** Wiadomość czatu ekipy: osoby (dymek z podpisem i godziną), komunikat o składzie albo karta Wodzireja. */
export function ChatMessage({ message, crew, info, now }: Props) {
  const time = <time dateTime={message.sentAt}>{messageTime(message.sentAt, now)}</time>;
  if (message.kind === "user") {
    const mine = message.isMe;
    return (
      <div className={cn(bubble, enter, mine ? mineBubble : "self-start border-2 border-input bg-card")}>
        <span className={cn(author, mine ? "text-primary-foreground/80" : "text-muted-foreground")}>{authorLabel(message)}</span>
        <span className="whitespace-pre-line">{message.text}</span>
        <span className={cn("self-end text-xs", mine ? "text-primary-foreground/70" : "text-muted-foreground")}>{time}</span>
      </div>
    );
  }

  const notice = noticeText(message);
  if (notice) {
    return (
      <p className={cn(enter, "self-center bg-card px-3 py-1 text-center text-meta text-muted-foreground")}>
        {notice} · {time}
      </p>
    );
  }

  const card = hostCard(message, crew, info);
  if (!card) return null; // rodzaj, którego ta wersja frontu nie zna (nowszy backend)
  return (
    <div className={cn(enter, "flex flex-col gap-2 border-2 border-input bg-secondary px-4 py-3 leading-snug")}>
      <div className="flex items-center gap-2 text-meta font-bold text-primary-ink">
        <Icon name="record_voice_over" size={22} />
        {HOST}
        <span className="ml-auto text-xs font-semibold">{time}</span>
      </div>
      <p className="text-pretty">{card.text}</p>
      <div className="flex flex-col gap-1 text-meta font-semibold">
        <span className="flex gap-1.5">
          <Icon name="location_on" size={18} className="text-primary-ink" />
          {card.meetingPoint}
        </span>
        <span className="flex gap-1.5">
          <Icon name="schedule" size={18} className="text-primary-ink" />
          {card.time}
        </span>
      </div>
    </div>
  );
}

/** Moja wiadomość w drodze do serwera; po zapisie zastępuje ją prawdziwa (z id i godziną). */
export function PendingMessage({ text, label }: { text: string; label: string }) {
  return (
    <div className={cn(bubble, mineBubble, "opacity-70")}>
      <span className={cn(author, "text-primary-foreground/80")}>{label}</span>
      <span className="whitespace-pre-line">{text}</span>
      <span className="self-end text-xs text-primary-foreground/70">Wysyłanie…</span>
    </div>
  );
}
