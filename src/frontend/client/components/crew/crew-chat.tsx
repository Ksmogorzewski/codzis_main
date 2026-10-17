import { type FormEvent, useEffect, useReducer, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { chatReducer, initialChat } from "@/lib/crew-chat";
import { DEMO_CREW, DEMO_SEED, demoScript } from "@/lib/crew-demo";
import { cn } from "@/lib/utils";
import { ChatMessage } from "./chat-message";
import { ColorCard } from "./color-card";

type Props = { eventTitle: string; category: string; className?: string };

// Czat mikro-ekipy wydarzenia (mockup_czatu_warsawnow_2). Ekran: components/crew/crew-chat-screen.tsx.
export function CrewChat({ eventTitle, category, className }: Props) {
  const [state, dispatch] = useReducer(chatReducer, DEMO_SEED, initialChat);
  const [text, setText] = useState("");
  const [cardOpen, setCardOpen] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const openCardRef = useRef<HTMLButtonElement>(null);
  const crew = DEMO_CREW;

  // Po odblokowaniu: odpowiedzi ekipy ze scenariusza demo (do zastąpienia wiadomościami z API).
  useEffect(() => {
    if (state.locked) return;
    let at = 0;
    const timers = demoScript(category).map(({ afterMs, message, beacon }) => {
      at += afterMs;
      return setTimeout(() => dispatch({ type: "receive", message, beacon }), at);
    });
    return () => timers.forEach(clearTimeout);
  }, [state.locked, category]);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [state.messages.length]);

  const send = (e: FormEvent) => {
    e.preventDefault();
    dispatch({ type: "send", text });
    setText("");
  };

  const closeCard = () => {
    setCardOpen(false);
    requestAnimationFrame(() => openCardRef.current?.focus());
  };

  return (
    <>
      {cardOpen && <ColorCard onClose={closeCard} />}
      <Card role="region" aria-labelledby="crew-title" className={className}>
        <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <h1 id="crew-title" className="text-title font-bold text-pretty">
              Ekipa: {eventTitle}
            </h1>
            <div className="mt-2 flex flex-wrap gap-2" aria-label="Tagi">
              <Badge>{category}</Badge>
            </div>
          </div>
          <Badge variant="success" size="lg">
            <Icon name="group" size={18} />
            {crew.members}/{crew.capacity} osoby
          </Badge>
        </div>

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
                "flex w-full flex-col items-center gap-3 rounded-2xl border bg-card px-5 py-6 text-center shadow-xl transition-transform duration-250",
                !state.locked && "translate-y-4",
              )}
            >
              <span className="flex size-12 items-center justify-center rounded-full bg-primary-soft text-primary-ink">
                <Icon name="forum" size={24} />
              </span>
              <h2 id="icebreaker-title" className="text-title font-bold">
                Lodołamacz
              </h2>
              <p className="leading-snug">
                Zanim dołączysz, odpowiedz: <strong>{crew.icebreaker}</strong>
              </p>
              <p className="text-meta text-muted-foreground">Napisz odpowiedź na dole, aby odblokować czat.</p>
            </div>
          </div>
        </div>

        {state.beacon && (
          <div className="border-t px-4 pt-3">
            <Button
              ref={openCardRef}
              variant="brand"
              className="w-full motion-safe:animate-pop"
              onClick={() => setCardOpen(true)}
            >
              <Icon name="location_on" size={22} filled />
              Pokaż Kartę Koloru
            </Button>
          </div>
        )}

        <form onSubmit={send} className={cn("flex gap-2 px-4 py-3", !state.beacon && "border-t")}>
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={state.locked ? "Odpowiedz na lodołamacz…" : "Napisz wiadomość…"}
            aria-label="Wiadomość"
            enterKeyHint="send"
            className="h-12 text-base"
          />
          <Button type="submit" size="icon" className="size-12 rounded-md" aria-label="Wyślij">
            <Icon name="send" size={22} filled />
          </Button>
        </form>
      </Card>
    </>
  );
}
