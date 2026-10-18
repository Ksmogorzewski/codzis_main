// Dane konta w profilu: nazwisko, data urodzenia i zdjęcie (PUT /api/me, /api/me/photo).
// Imię zostaje z rejestracji albo Google (niezmienne - widzą je inni zapisani), więc tu go nie ma.
// Walidacja jak w src/client_api/account.py.
import { initials } from "../../shared/format";

export const MAX_LAST_NAME = 60;
export const MIN_BIRTH_DATE = "1900-01-01";
// Przed wysyłką zdjęcie zmniejszamy do PHOTO_SIZE px (JPEG), więc źródło może być duże (zdjęcie z telefonu).
export const MAX_PHOTO_SOURCE_BYTES = 20 * 1024 * 1024;
export const PHOTO_SIZE = 512;

export type AccountInput = { lastName: string | null; birthDate: string | null };

const normalize = (value: string) => value.split(/\s+/).filter(Boolean).join(" ");

/** Body PUT /api/me: puste pole = usuń je z profilu. */
export const accountInput = (lastName: string, birthDate: string): AccountInput => ({
  lastName: normalize(lastName) || null,
  birthDate: birthDate || null,
});

export function lastNameError(value: string): string | null {
  return normalize(value).length > MAX_LAST_NAME ? `Nazwisko może mieć najwyżej ${MAX_LAST_NAME} znaków.` : null;
}

/** `today` = dzisiejsza data w Warszawie (RRRR-MM-DD); pusta data jest w porządku (pole opcjonalne). */
export function birthDateError(value: string, today: string): string | null {
  if (!value) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !isRealDate(value)) return "Podaj poprawną datę urodzenia.";
  if (value < MIN_BIRTH_DATE || value > today) return "Data urodzenia musi być między 1900 r. a dziś.";
  return null;
}

function isRealDate(iso: string): boolean {
  const d = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso;
}

/** Wiek w pełnych latach (obie daty RRRR-MM-DD). */
export function ageOn(birthDate: string, today: string): number {
  const [by, bm, bd] = birthDate.split("-").map(Number) as [number, number, number];
  const [ty, tm, td] = today.split("-").map(Number) as [number, number, number];
  return ty - by - (tm < bm || (tm === bm && td < bd) ? 1 : 0);
}

export const fullName = (first: string | null, last: string | null) => [first, last].filter(Boolean).join(" ");

export const avatarInitials = (first: string | null, last: string | null) => initials(fullName(first, last));

export function photoFileError(file: { type: string; size: number }): string | null {
  if (!file.type.startsWith("image/")) return "Wybierz plik ze zdjęciem.";
  if (file.size > MAX_PHOTO_SOURCE_BYTES) return "To zdjęcie jest za duże (maks. 20 MB).";
  return null;
}

/** Wymiary po zmniejszeniu dłuższego boku do `max` px; małych zdjęć nie powiększamy. */
export function fitWithin(width: number, height: number, max: number): { width: number; height: number } {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

// --- przeglądarka ---

/** Zdjęcie zmniejszone do PHOTO_SIZE px jako JPEG (mniejszy upload, szybsze wczytywanie list). */
export async function shrinkPhoto(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const { width, height } = fitWithin(bitmap.width, bitmap.height, PHOTO_SIZE);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob"))), "image/jpeg", 0.85),
  );
}

/** Upload formularzem z POST /api/me/photo (presigned POST do S3: najpierw pola, plik na końcu). */
export async function uploadToS3(upload: { url: string; fields: Record<string, string> }, file: Blob): Promise<boolean> {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) form.append(name, value);
  form.append("file", file);
  try {
    return (await fetch(upload.url, { method: "POST", body: form })).ok;
  } catch {
    return false;
  }
}
