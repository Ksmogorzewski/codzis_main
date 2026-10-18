import { describe, expect, it, vi } from "vitest";
import { createNamePrompt } from "./name-prompt";

describe("prośba o imię (409 name_required)", () => {
  it("otwiera się na żądanie i powiadamia subskrybentów", () => {
    const prompt = createNamePrompt();
    const listener = vi.fn();
    const unsubscribe = prompt.subscribe(listener);
    expect(prompt.isOpen()).toBe(false);
    prompt.open();
    prompt.open(); // drugi błąd z innego zapytania nie zmienia stanu
    expect(prompt.isOpen()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    prompt.close();
    expect(prompt.isOpen()).toBe(false);
    unsubscribe();
    prompt.open();
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
