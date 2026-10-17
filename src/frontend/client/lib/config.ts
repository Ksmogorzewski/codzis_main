// Konfiguracja runtime z config.js (Terraform: local.client_app_config w infra/client_site.tf,
// lokalnie scripts/frontend-dev.sh). Nie jest bundlowana - ładuje ją <script src="/config.js"> w index.html.
import { z } from "zod";
import { err, ok, type Result } from "./result";

const ClientConfigSchema = z.object({
  region: z.string().min(1),
  userPoolId: z.string().min(1),
  clientId: z.string().min(1),
  apiUrl: z.string().min(1).transform((url) => url.replace(/\/+$/, "")),
  partnerPortal: z.string().default(""),
});

export type ClientConfig = z.infer<typeof ClientConfigSchema>;

export const CONFIG_ERROR = "Brak konfiguracji aplikacji (config.js). Odśwież stronę albo skontaktuj się z nami.";

/** Sprawdza kształt window.APP_CONFIG. Czysta funkcja (testy). */
export function parseConfig(raw: unknown): Result<ClientConfig, string> {
  const parsed = ClientConfigSchema.safeParse(raw);
  return parsed.success ? ok(parsed.data) : err(CONFIG_ERROR);
}

let cached: ClientConfig | null = null;

/** Konfiguracja albo błąd (np. brak config.js lokalnie). Wywołuje ją strażnik w __root.tsx. */
export function loadConfig(): Result<ClientConfig, string> {
  if (cached) return ok(cached);
  const r = parseConfig(typeof window === "undefined" ? undefined : window.APP_CONFIG);
  if (r.error === null) cached = r.data;
  return r;
}

/** Konfiguracja po sprawdzeniu w __root.tsx; rzuca, gdy jej brak (błąd programisty, nie użytkownika). */
export function config(): ClientConfig {
  const r = loadConfig();
  if (r.error !== null) throw new Error(r.error);
  return r.data;
}
