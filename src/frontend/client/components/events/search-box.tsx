import { type FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { MAX_QUERY, normalizeQuery } from "@/lib/search";

type Props = { value: string; onChange: (q: string) => void };

const DEBOUNCE_MS = 450;

/**
 * Wyszukiwarka: wpisany tekst trafia do adresu (?q=) po chwili bez pisania albo od razu po Enter.
 * Zmiana z zewnątrz (reset filtrów, przycisk wstecz) nadpisuje pole.
 */
export function SearchBox({ value, onChange }: Props) {
  const [input, setInput] = useState(value);
  const pushed = useRef(value);

  useEffect(() => {
    if (value === pushed.current) return;
    pushed.current = value;
    setInput(value);
  }, [value]);

  useEffect(() => {
    const next = normalizeQuery(input);
    if (next === pushed.current) return;
    const timer = setTimeout(() => {
      pushed.current = next;
      onChange(next);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input, onChange]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = normalizeQuery(input);
    pushed.current = next;
    onChange(next);
  }

  function clear() {
    setInput("");
    pushed.current = "";
    onChange("");
  }

  return (
    <form role="search" onSubmit={submit} className="relative flex min-w-0 flex-1 items-center">
      <Icon name="search" size={22} className="pointer-events-none absolute left-3.5 text-muted-foreground" />
      <Input
        type="search"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Np. jazz, joga, ceramika"
        aria-label="Szukaj wydarzeń"
        maxLength={MAX_QUERY}
        enterKeyHint="search"
        className="h-12 pr-12 pl-11 text-base [&::-webkit-search-cancel-button]:hidden"
      />
      {input && (
        <Button type="button" variant="ghost" size="icon" aria-label="Wyczyść wyszukiwanie" onClick={clear} className="absolute right-0.5">
          <Icon name="close" size={20} />
        </Button>
      )}
    </form>
  );
}
