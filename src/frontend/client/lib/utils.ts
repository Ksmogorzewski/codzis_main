import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Łączy klasy Tailwinda; późniejsze nadpisują wcześniejsze (np. wariant + className). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
