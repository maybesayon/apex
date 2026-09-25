import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** $1,234.56 */
export function money(value: number | null | undefined, dp = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

/** +1.23% — always signed, so direction reads without needing colour. */
export function percent(value: number | null | undefined, dp = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(dp)}%`;
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
}

/** Tailwind colour class for a gain/loss, or muted when unknown. */
export function toneClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value))
    return "text-muted";
  return value >= 0 ? "text-up" : "text-down";
}
