// Czat ekipy (src/client_api/crews.py): zapisani na wydarzenie łączą się w ekipy do 4 osób, każda ma własny czat.
// Wiadomości osób i komunikaty Wodzireja składane z danych wydarzenia (bez AI i bez zmyślonych odpowiedzi).
// Czyste funkcje: łączenie kolejnych odpowiedzi API (odpytywanie), teksty komunikatów i podglądów, skład ekipy,
// nieprzeczytane.
import { plural } from "../../shared/format";
import { attendeeLabel } from "./community";
import { warsawDate } from "./events";
import type { Crew, CrewLast, CrewMember, CrewMessage, MyCrew, MyCrews } from "./schemas";

/** Komunikaty z danych wydarzenia (bez AI) podpisujemy nazwą serwisu. */
export const HOST = "Wodzirej WarsawNow";

/** Wielkość ekipy, zanim przyjdzie odpowiedź API (jak CREW_SIZE w src/client_api/crews.py). */
export const CREW_CAPACITY = 4;

/** Najdłuższa wiadomość (jak MAX_MESSAGE w crews.py). */
export const MAX_MESSAGE = 500;

/** Otwarty czat pyta o nowe wiadomości co 3 s, plakietki co 30 s (tylko przy widocznej karcie). */
export const CHAT_POLL_MS = 3000;
export const CREWS_POLL_MS = 30_000;

// sentAt to ISO 8601 UTC w jednym formacie, więc porównanie tekstów = porównanie czasu
const byTime = (a: CrewMessage, b: CrewMessage) => a.sentAt.localeCompare(b.sentAt) || a.id.localeCompare(b.id);

/**
 * Kolejna odpowiedź GET …/crew -> stan czatu. Z ?after= serwer oddaje też do 15 s starsze wiadomości, więc
 * łączymy po id (bez powtórek) i sortujemy po czasie. Inna ekipa (wyjście i ponowne dołączenie) = nowa rozmowa.
 */
export function mergeCrew(prev: Crew | undefined, next: Crew): Crew {
  const same = prev?.crew === next.crew;
  const messages = new Map([...(same && prev ? prev.messages : []), ...next.messages].map((m) => [m.id, m]));
  const cursors = [same ? prev?.cursor : null, next.cursor].filter((c): c is string => Boolean(c)).sort();
  return { ...next, messages: [...messages.values()].sort(byTime), cursor: cursors.at(-1) ?? null };
}

/** Moja wysłana wiadomość od razu w czacie (zanim wróci z odpytywania); pierwsza odblokowuje czat. */
export function withMessage(crew: Crew, message: CrewMessage): Crew {
  if (crew.messages.some((m) => m.id === message.id)) return { ...crew, answered: true };
  return {
    ...crew,
    answered: true,
    messageCount: crew.messageCount + 1,
    messages: [...crew.messages, message].sort(byTime),
  };
}

/** Podpis wiadomości osoby: moje „Ola K. (Ty)”, cudze imię, bez imienia „Ktoś”. */
export const authorLabel = (m: Pick<CrewLast, "name" | "isMe">): string => attendeeLabel({ name: m.name, isMe: m.isMe });

const who = (m: Pick<CrewLast, "name">) => m.name?.trim() || "Ktoś";

/** Komunikat o składzie (jedna linia na środku czatu); null = to nie komunikat o składzie. */
export function noticeText(m: CrewLast): string | null {
  if (m.kind === "joined") return m.isMe ? "Dołączasz do ekipy" : `${who(m)} dołącza do ekipy`;
  if (m.kind === "left") return m.isMe ? "Wychodzisz z ekipy" : `${who(m)} wychodzi z ekipy`;
  return null;
}

/** Dane wydarzenia do komunikatów Wodzireja: kategoria, miejsce (placeLabel) i termin (slotLabel). */
export type MeetingInfo = { category: string; place: string | null; when: string | null };

export type HostCard = { text: string; meetingPoint: string; time: string };

/**
 * Karta Wodzireja: „welcome” (nowa ekipa: kto ją zaczął i lodołamacz) albo „full” (komplet). Punkt i czas
 * zbiórki tylko z danych wydarzenia - bez zmyślonych miejsc i godzin. null = inny rodzaj wiadomości.
 */
export function hostCard(m: CrewLast, crew: Pick<Crew, "capacity" | "icebreaker">, info: MeetingInfo): HostCard | null {
  const meeting = {
    meetingPoint: info.place ? `Punkt zbiórki: przy wejściu, ${info.place}` : "Punkt zbiórki: przy wejściu na miejsce wydarzenia",
    time: info.when ? `${info.when} · zbiórka 15 minut wcześniej` : "Zbiórka 15 minut przed startem",
  };
  if (m.kind === "welcome") {
    const start = m.isMe ? "Zaczynasz ekipę na to wydarzenie" : `${who(m)} zaczyna ekipę na to wydarzenie`;
    const question = crew.icebreaker ? ` Na dobry początek: ${crew.icebreaker}` : "";
    return { text: `${start}. Zbieramy do ${crew.capacity} osób, które idą razem.${question}`, ...meeting };
  }
  if (m.kind === "full") {
    return { text: `Mamy komplet ${crew.capacity} osób! Łączy Was kategoria „${info.category}”.`, ...meeting };
  }
  return null;
}

/** Ostatnia wiadomość w jednej linii (wiersz „Czat ekipy” na „Twoje”, toast o nowej wiadomości). */
export function messagePreview(m: CrewLast): string {
  if (m.kind === "user") return `${m.isMe ? "Ty" : who(m)}: ${m.text ?? ""}`;
  if (m.kind === "welcome") return `${HOST}: ekipa wystartowała`;
  if (m.kind === "full") return `${HOST}: mamy komplet!`;
  return noticeText(m) ?? "";
}

const timeFormat = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", hour: "2-digit", minute: "2-digit" });
const dayFormat = new Intl.DateTimeFormat("pl-PL", { timeZone: "Europe/Warsaw", day: "2-digit", month: "2-digit" });

/** Czas wiadomości (po warszawsku): dziś „18:05”, inny dzień „14.10, 18:05”; zły zapis -> "". */
export function messageTime(sentAt: string, now: Date): string {
  const at = new Date(sentAt);
  if (Number.isNaN(at.getTime())) return "";
  const time = timeFormat.format(at);
  return warsawDate(at) === warsawDate(now) ? time : `${dayFormat.format(at)}, ${time}`;
}

/** Imiona pozostałych członków ekipy (bez mnie), w kolejności dołączania. */
export const otherNames = (members: readonly CrewMember[]): string[] => members.filter((m) => !m.isMe).map((m) => m.name);

/** „Ty, Piotr, Kamil i Antek” — skład ekipy w jednej linii (ja zawsze pierwszy). */
export function membersLine(others: readonly string[]): string {
  const all = ["Ty", ...others];
  return all.length === 1 ? "Ty" : `${all.slice(0, -1).join(", ")} i ${all.at(-1)}`;
}

/** „2/4 osoby” na plakietce w nagłówku czatu. */
export const crewSizeLabel = (size: number, capacity: number) => `${size}/${capacity} osoby`;

/** „1 nowa wiadomość”, „3 nowe wiadomości”, „5 nowych wiadomości”. */
export const unreadLabel = (n: number) => plural(n, "nowa wiadomość", "nowe wiadomości", "nowych wiadomości");

const toLast = (m: CrewMessage): CrewLast => ({
  kind: m.kind,
  userId: m.userId,
  name: m.name,
  text: m.text,
  sentAt: m.sentAt,
  isMe: m.isMe,
});

/**
 * Otwarty czat (GET …/crew oznacza wszystko jako przeczytane) -> wiersz tej ekipy w GET /api/me/crews bez
 * nieprzeczytanych, z aktualnym składem i ostatnią wiadomością: plakietki spadają od razu, bez czekania 30 s.
 * Ekipy spoza listy (pierwsze wejście) nie dokładamy - hook unieważnia wtedy listę.
 */
export function markCrewRead(data: MyCrews | undefined, eventId: string, crew: Crew): MyCrews | undefined {
  if (!data?.items.some((c) => c.eventId === eventId)) return data;
  const last = crew.messages.at(-1);
  const items = data.items.map((c) =>
    c.eventId === eventId
      ? { ...c, crew: crew.crew, members: crew.members, messageCount: crew.messageCount, unread: 0, last: last ? toLast(last) : c.last }
      : c,
  );
  return { items, unread: items.reduce((sum, c) => sum + c.unread, 0) };
}

/** Ekipy, w których od poprzedniego odpytania przybyło nieprzeczytanych cudzych wiadomości (toast). */
export function arrivals(prev: MyCrews | undefined, next: MyCrews): MyCrew[] {
  if (!prev) return [];
  const before = new Map(prev.items.map((c) => [c.eventId, c.unread]));
  return next.items.filter((c) => c.unread > (before.get(c.eventId) ?? 0) && c.last !== null && !c.last.isMe);
}
