import { type FormEvent, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { errorText } from "@/components/layout/route-error";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { useSendMessage } from "@/hooks/use-send-message.mutation";
import { currentDisplayName } from "@/lib/auth";
import { authorLabel, MAX_MESSAGE, type MeetingInfo } from "@/lib/crew-chat";
import type { Crew } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { ChatMessage, PendingMessage } from "./chat-message";
import { ColorCard } from "./color-card";

type Props = {
  id: string;
  /** Moja ekipa z wiadomościami (hooks/use-crew.query.ts - odpytywanie co 3 s). */
  crew: Crew;
  /** Dane wydarzenia do kart Wodzireja (punkt i czas zbiórki). */
  info: MeetingInfo;
};

// Bliżej dołu niż tyle px = czytam najnowsze, więc nowa wiadomość przewija czat; wyżej - czytam historię.
const STICK_PX = 80;

// Czat mikro-ekipy wydarzenia (mockup_czatu_warsawnow_2), ekran: components/crew/crew-chat-screen.tsx.
// Dopóki nic nie napiszę (crew.answered), czat zasłania lodołamacz - pierwsza wiadomość to odpowiedź na niego.
export function CrewChat({ id, crew, info }: Props) {
  const send = useSendMessage(id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const openCardRef = useRef<HTMLButtonElement>(null);
  const locked = !crew.answered && pending === null;
  const now = new Date();

  useEffect(() => {
    const log = logRef.current;
    if (log && stick.current) log.scrollTop = log.scrollHeight;
  }, [crew.messages.length, pending]);

  const onScroll = () => {
    const log = logRef.current;
    if (log) stick.current = log.scrollHeight - log.scrollTop - log.clientHeight < STICK_PX;
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value || pending !== null) return;
    stick.current = true;
    setPending(value);
    setText("");
    send.mutate(value, {
      onSettled: () => setPending(null),
      onError: (error) => {
        setText((current) => current || value); // tekst wraca do pola, jeśli nie wpisano nic nowego
        toast.error(errorText(error, "Nie udało się wysłać wiadomości. Spróbuj ponownie."));
      },
    });
  };

  const closeCard = () => {
    setCardOpen(false);
    requestAnimationFrame(() => openCardRef.current?.focus());
  };

  return (
    <>
      {cardOpen && <ColorCard onClose={closeCard} />}
      <div className="relative min-h-0 flex-1 bg-secondary">
        <div
          ref={logRef}
          onScroll={onScroll}
          role="log"
          aria-live="polite"
          aria-label="Wiadomości ekipy"
          className="flex h-full flex-col gap-3 overflow-y-auto overscroll-contain p-4"
        >
          {crew.messages.map((m) => (
            <ChatMessage key={m.id} message={m} crew={crew} info={info} now={now} />
          ))}
          {pending !== null && <PendingMessage text={pending} label={authorLabel({ name: currentDisplayName(), isMe: true })} />}
        </div>

        <div
          aria-hidden={!locked}
          className={cn(
            "absolute inset-0 z-10 flex items-center justify-center bg-overlay p-6 transition-opacity duration-250",
            !locked && "pointer-events-none opacity-0",
          )}
        >
          <div
            role="group"
            aria-labelledby="icebreaker-title"
            className={cn(
              "flex w-full max-w-md flex-col items-center gap-3 border-2 border-input bg-card px-5 py-6 text-center transition-transform duration-250",
              !locked && "translate-y-4",
            )}
          >
            <span className="flex size-12 items-center justify-center bg-foreground text-background">
              <Icon name="forum" size={24} />
            </span>
            <h2 id="icebreaker-title" className="text-title font-bold">
              Lodołamacz
            </h2>
            <p className="leading-snug text-pretty">
              Zanim dołączysz, odpowiedz: <strong>{crew.icebreaker}</strong>
            </p>
            <p className="text-meta text-muted-foreground">Napisz odpowiedź na dole, aby odblokować czat.</p>
          </div>
        </div>
      </div>

      <div className="border-t bg-card">
        {!locked && crew.members.length > 1 && (
          <div className="px-4 pt-3">
            <Button
              ref={openCardRef}
              variant="brand"
              size="lg"
              className="w-full motion-safe:animate-pop"
              onClick={() => setCardOpen(true)}
            >
              <Icon name="location_on" size={22} filled />
              Pokaż Kartę Koloru
            </Button>
          </div>
        )}
        <form onSubmit={submit} className="flex gap-2 px-4 py-3">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={locked ? "Odpowiedz na lodołamacz…" : "Napisz wiadomość…"}
            aria-label="Wiadomość"
            maxLength={MAX_MESSAGE}
            enterKeyHint="send"
            autoComplete="off"
            className="h-12 text-base"
          />
          <Button
            type="submit"
            size="icon"
            className="size-12"
            aria-label="Wyślij"
            disabled={pending !== null}
            aria-busy={pending !== null || undefined}
          >
            <Icon name="send" size={22} filled />
          </Button>
        </form>
      </div>
    </>
  );
}
