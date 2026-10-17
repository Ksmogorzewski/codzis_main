// Kontrakt API partnera (src/api/handler.py)

export type FormOptions = {
  cost: string[];
  registration: string[];
  setting: string[];
  audience: string[];
  accessibility: string[];
};

export type Profile = {
  partnerId: string;
  partnerName: string;
  credits: number;
  eventCost: number;
  formOptions: FormOptions;
};

export type Tags = Record<string, string | string[] | null>;

// Zgłoszenie partnera = rekord eventu w schemacie v1 (src/importer/schema.py) + status
export type Submission = {
  id: string;
  status: "queued" | "published";
  title: string;
  lead: string | null;
  text: string | null;
  url: string | null;
  category: { id: string | null; name: string }[];
  district: string | null;
  venue: { name: string | null; address: string | null };
  occurrences: { start: string; end: string | null; allDay: boolean }[];
  startsAt: string | null;
  endsAt: string | null;
  imageUrl: string | null;
  attributes: { price?: { min: number | null; max: number | null; currency: string } | null; ticketUrl?: string | null };
  declared?: Partial<Record<"cost" | "registration" | "setting", string>> & Partial<Record<"audience" | "accessibility", string[]>>;
  tags?: Tags;
  createdAt: string;
};

export type Payment = {
  id: string;
  package: string;
  packageName: string;
  credits: number;
  amount: number;
  currency: string;
  status: "pending" | "paid" | "cancelled";
  createdAt: string;
  redirectUrl?: string;
};

export type CreatedEvent = { id: string; upload: { url: string; fields: Record<string, string> } };
