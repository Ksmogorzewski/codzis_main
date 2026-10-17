// Wspólne dla portalu i mock bramki.
const CONFIG = window.APP_CONFIG;
const KEY_STORAGE = "apiKey";

const session = {
  get() {
    try {
      return sessionStorage.getItem(KEY_STORAGE);
    } catch {
      return null;
    }
  },
  set(key) {
    try {
      key ? sessionStorage.setItem(KEY_STORAGE, key) : sessionStorage.removeItem(KEY_STORAGE);
    } catch {}
  },
};

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(method, path, body, apiKey = session.get()) {
  const res = await fetch(`${CONFIG.apiUrl}${path}`, {
    method,
    headers: { "Content-Type": "application/json", "x-api-key": apiKey || "" },
    body: body && JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 403) throw new ApiError(403, "Nieprawidłowy klucz API");
  if (res.status === 429) throw new ApiError(429, "Przekroczono limit żądań, spróbuj za chwilę");
  if (!res.ok) {
    const message = data.error || data.message || `HTTP ${res.status}`;
    throw new ApiError(res.status, data.fields ? `${message}: ${data.fields.map(fieldLabel).join(", ")}` : message);
  }
  return data;
}

const FIELD_LABELS = {
  title: "tytuł", lead: "krótki opis", text: "pełny opis", category: "kategoria", url: "link",
  startsAt: "początek", endsAt: "koniec", venue: "nazwa miejsca", street: "ulica",
  streetNumber: "numer", district: "dzielnica",
};
const fieldLabel = (name) => FIELD_LABELS[name] || name;

// "2027-01-29T19:00" z <input type="datetime-local"> -> ISO z offsetem strefy przeglądarki
function withTimezone(local) {
  const offset = -new Date(local).getTimezoneOffset();
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  const seconds = local.length === 16 ? ":00" : "";
  return `${local}${seconds}${offset >= 0 ? "+" : "-"}${pad(offset / 60)}:${pad(offset % 60)}`;
}

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  node.append(...children.filter((c) => c != null));
  return node;
}

const formatMoney = (amount, currency = CONFIG.currency) =>
  new Intl.NumberFormat("pl-PL", { style: "currency", currency }).format(amount);

const formatDate = (iso) =>
  new Date(iso).toLocaleString("pl-PL", { dateStyle: "medium", timeStyle: "short" });

// Odmiana: plural(1, "kredyt", "kredyty", "kredytów") -> "1 kredyt"
function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (n === 1) return `${n} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

const creditsLabel = (n) => plural(n, "kredyt", "kredyty", "kredytów");

const sortedPackages = () =>
  Object.entries(CONFIG.packages)
    .map(([id, p]) => ({ id, ...p }))
    .sort((a, b) => a.credits - b.credits);

const SUBMISSION_STATUS = { queued: "W kolejce", published: "Opublikowane" };
const PAYMENT_STATUS = { pending: "Oczekuje", paid: "Opłacona", cancelled: "Anulowana" };
