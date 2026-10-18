import { type FormEvent, useEffect, useReducer, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { type ChatMessageInput, chatReducer, initialChat, timeline } from "@/lib/crew-chat";
import { DEMO_CREW, demoScript } from "@/lib/crew-demo";
import { cn } from "@/lib/utils";
import { ChatMessage, TypingIndicator } from "./chat-message";
import { ColorCard } from "./color-card";

type Props = {
  /** Pozostali członkowie ekipy (bez mnie): imiona zapisanych, uzupełnione demo. */
  members: string[];
  /** Wiadomości, które już są w czacie (DEMO: demoInbox - ta sama rozmowa co na zakładce „Twoje”). */
  seed: ChatMessageInput[];
  /** Podpis moich wiadomości (ownLabel). */
  myLabel: string;
  category: string;
  place: string | null;
  when: string | null;
};

// Czat mikro-ekipy wydarzenia (mockup_czatu_warsawnow_2). Ekran: components/crew/crew-chat-screen.tsx.
// DEMO: wiadomości i odpowiedzi to scenariusz z lib/crew-demo.ts odtwarzany lokalnie (bez backendu).
export function CrewChat({ members, seed, myLabel, category, place, when }: Props) {
  // Scenariusz liczony raz przy wejściu: zmiana listy zapisanych w tle nie przestawia rozmowy.
  const [plan] = useState(() => ({
    seed,
    steps: timeline(demoScript({ members, category, place, when })),
  }));
  const [state, dispatch] = useReducer(chatReducer, plan.seed, initialChat);
  const [text, setText] = useState("");
  const [cardOpen, setCardOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const openCardRef = useRef<HTMLButtonElement>(null);

  // Po odblokowaniu: „X pisze…” i odpowiedzi ekipy w czasie (DEMO; docelowo wiadomości z API).
  useEffect(() => {
    if (state.locked) return;
    const timers = plan.steps.map(({ at, action }) => setTimeout(() => dispatch(action), at));
    return () => timers.forEach(clearTimeout);
  }, [state.locked, plan]);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [state.messages.length, state.typing]);

  const send = (e: FormEvent) => {
    e.preventDefault();
    dispatch({ type: "send", text, author: myLabel });
    setText("");
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
          role="log"
          aria-live="polite"
          aria-label="Wiadomości ekipy"
          className="flex h-full flex-col gap-3 overflow-y-auto overscroll-contain p-4"
        >
          {state.messages.map((m) => (
            <ChatMessage key={m.id} message={m} />
          ))}
          {state.typing && <TypingIndicator who={state.typing} />}
        </div>

        <div
          aria-hidden={!state.locked}
          className={cn(
            "absolute inset-0 z-10 flex items-center justify-center bg-overlay p-6 transition-opacity duration-250",
            !state.locked && "pointer-events-none opacity-0",
          )}
        >
          <div
            role="group"
            aria-labelledby="icebreaker-title"
            className={cn(
              "flex w-full max-w-md flex-col items-center gap-3 rounded-2xl border bg-card px-5 py-6 text-center shadow-lg transition-transform duration-250",
              !state.locked && "translate-y-4",
            )}
          >
            <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary-ink">
              <Icon name="forum" size={24} />
            </span>
            <h2 id="icebreaker-title" className="text-title font-bold">
              Lodołamacz
            </h2>
            <p className="leading-snug text-pretty">
              Zanim dołączysz, odpowiedz: <strong>{DEMO_CREW.icebreaker}</strong>
            </p>
            <p className="text-meta text-muted-foreground">Napisz odpowiedź na dole, aby odblokować czat.</p>
          </div>
        </div>
      </div>

      <div className="border-t bg-card">
        {state.beacon && (
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
        <form onSubmit={send} className="flex gap-2 px-4 py-3">
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={state.locked ? "Odpowiedz na lodołamacz…" : "Napisz wiadomość…"}
            aria-label="Wiadomość"
            enterKeyHint="send"
            autoComplete="off"
            className="h-12 text-base"
          />
          <Button type="submit" size="icon" className="size-12 rounded-md" aria-label="Wyślij">
            <Icon name="send" size={22} filled />
          </Button>
        </form>
      </div>
    </>
  );
}
