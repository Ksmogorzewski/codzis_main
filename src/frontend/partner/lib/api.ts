import { config } from "./config";
import { session } from "./session";

export class ApiError extends Error {
  constructor(public status: number, message: string, public fields: string[] = []) {
    super(message);
  }
}

// Nazwy pól z walidacji API (src/api/handler.py) -> etykiety formularza
export const FIELD_LABELS: Record<string, string> = {
  title: "nazwa", lead: "krótki opis", text: "opis", category: "kategoria", url: "link do strony",
  startsAt: "początek", endsAt: "koniec", venue: "nazwa miejsca", street: "ulica", streetNumber: "numer",
  district: "dzielnica", setting: "gdzie się odbywa", cost: "wstęp", priceMin: "cena od", priceMax: "cena do",
  registration: "zapisy i bilety", ticketUrl: "link do biletów", audience: "dla kogo", accessibility: "dostępność",
};

export async function api<T>(method: "GET" | "POST", path: string, body?: unknown, apiKey = session.get()): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${config().apiUrl}${path}`, {
      method,
      headers: { "Content-Type": "application/json", "x-api-key": apiKey ?? "" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Brak połączenia z serwerem. Spróbuj ponownie.");
  }
  const data = (await res.json().catch(() => ({}))) as { error?: string; message?: string; fields?: string[] };
  if (res.status === 403) throw new ApiError(403, "Nieprawidłowy klucz API");
  if (res.status === 429) throw new ApiError(429, "Przekroczono limit żądań, spróbuj za chwilę");
  if (!res.ok) {
    const fields = data.fields ?? [];
    const message = data.error || data.message || `Błąd serwera (${res.status})`;
    throw new ApiError(res.status, fields.length ? `${message}: ${fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}` : message, fields);
  }
  return data as T;
}
