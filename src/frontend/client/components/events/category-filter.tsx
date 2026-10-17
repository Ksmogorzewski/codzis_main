import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CATEGORIES, CATEGORY_LABEL, type Category } from "@/lib/categories";

const isCategory = (v: string): v is Category => (CATEGORIES as readonly string[]).includes(v);

/** Chipy kategorii: Wszystko / Sport / Kultura / Rekreacja. */
export function CategoryFilter({ value, onChange }: { value: Category; onChange: (cat: Category) => void }) {
  return (
    <ToggleGroup
      type="single"
      variant="pill"
      aria-label="Kategoria"
      value={value}
      onValueChange={(v) => isCategory(v) && onChange(v)}
      className="-m-1.5 overflow-x-auto p-1.5 [scrollbar-width:none]"
    >
      {CATEGORIES.map((id) => (
        <ToggleGroupItem key={id} value={id}>
          {CATEGORY_LABEL[id]}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
