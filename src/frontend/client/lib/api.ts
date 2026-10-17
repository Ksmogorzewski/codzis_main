import { getIdToken } from "./auth";
import { config } from "./config";

export class ApiError extends Error {
  constructor(public status: number, message: string, public fields: string[] = []) {
    super(message);
  }
}

// Wywołanie API klienta z ID tokenem Cognito (weryfikuje go JWT authorizer w API Gateway)
export async function api<T>(method: "GET" | "PUT", path: string, body?: unknown): Promise<T> {
  const token = await getIdToken();
  if (!token) throw new ApiError(401, "Zaloguj się ponownie.");
  let res: Response;
  try {
    res = await fetch(`${config().apiUrl}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Brak połączenia z serwerem. Spróbuj ponownie.");
  }
  const data = (await res.json().catch(() => ({}))) as { error?: string; message?: string; fields?: string[] };
  if (res.status === 401) throw new ApiError(401, "Sesja wygasła – zaloguj się ponownie.");
  if (!res.ok) throw new ApiError(res.status, data.error || data.message || `Błąd serwera (${res.status})`, data.fields);
  return data as T;
}
