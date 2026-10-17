import { useRef } from "react";
import { Icon } from "@/components/ui/icon";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { chosenDayLabel, dateBounds } from "@/lib/events";

type Props<W extends string> = {
  /** Przyciski poza „Inny dzień” (np. Dziś / Jutro / Weekend). */
  options: readonly { id: W; label: string }[];
  /** Aktualny wybór; "date" = Inny dzień. */
  value: W | "date";
  date: string | undefined;
  onWhen: (when: W) => void;
  onDate: (date: string) => void;
};

/** Segment czasu z „Inny dzień” (natywny kalendarz; filtr zmienia się dopiero po wybraniu daty). */
export function WhenFilter<W extends string>({ options, value, date, onWhen, onDate }: Props<W>) {
  const dateInput = useRef<HTMLInputElement>(null);
  const now = new Date();
  const bounds = dateBounds(now);
  const openPicker = () => {
    const input = dateInput.current;
    if (!input) return;
    try {
      input.showPicker();
    } catch {
      input.focus();
      input.click();
    }
  };
  return (
    <div className="relative max-w-full">
      <ToggleGroup
        type="single"
        variant="segment"
        aria-label="Kiedy"
        value={value}
        onValueChange={(v) => {
          const picked = options.find((o) => o.id === v);
          if (picked) onWhen(picked.id);
        }}
        className="max-w-full overflow-x-auto [scrollbar-width:none]"
      >
        {options.map((o) => (
          <ToggleGroupItem key={o.id} value={o.id}>
            {o.label}
          </ToggleGroupItem>
        ))}
        <ToggleGroupItem value="date" onClick={openPicker}>
          <Icon name="calendar_month" size={18} />
          {date ? chosenDayLabel(date, now) : "Inny dzień"}
        </ToggleGroupItem>
      </ToggleGroup>
      <input
        ref={dateInput}
        type="date"
        min={bounds.min}
        max={bounds.max}
        value={date ?? ""}
        onChange={(e) => e.target.value && onDate(e.target.value)}
        tabIndex={-1}
        aria-label="Wybierz dzień"
        className="sr-only bottom-0 left-0"
      />
    </div>
  );
}
