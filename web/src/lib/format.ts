import type { Cell } from "../api/types";

const NUMBER = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });
const MONEY_SHORT = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2,
});
const PLAIN_COLUMN = /(^|_)(id|code|number|year|month|quarter|week|day|level|sku)$/i;

/** Table cell text: thousands separators for measures, ids and years as they are. */
export function formatCell(value: Cell, column = ""): string {
  if (value === null) return "NULL";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    return PLAIN_COLUMN.test(column) && Number.isInteger(value)
      ? String(value)
      : NUMBER.format(value);
  }
  return value;
}

/** Short axis labels for charts (1.2B, 350K). */
export function formatAxis(value: number): string {
  return Math.abs(value) >= 10_000 ? MONEY_SHORT.format(value) : NUMBER.format(value);
}

export function formatUsd(value: number): string {
  return value === 0 ? "$0" : `$${value.toFixed(value < 0.01 ? 6 : 4)}`;
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function isNumeric(value: Cell): value is number {
  return typeof value === "number";
}

/** A column name as words: "net_revenue_idr" -> "net revenue (IDR)". */
export function humanize(column: string): string {
  const idr = /_idr$/i.test(column);
  const words = column.replace(/_idr$/i, "").replace(/_/g, " ").trim();
  return idr ? `${words} (IDR)` : words;
}
