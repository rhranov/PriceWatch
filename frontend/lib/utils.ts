import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatEur(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(value);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Never";
  return format(new Date(iso), "dd MMM yyyy HH:mm");
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Never";
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}
