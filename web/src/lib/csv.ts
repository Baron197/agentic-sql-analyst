import type { Cell } from "../api/types";

// Cells starting with these can run as formulas in a spreadsheet (CSV injection).
// Result rows can hold untrusted text (support-ticket subjects), so such cells get a
// leading apostrophe, which spreadsheets show as plain text.
const FORMULA_START = /^[=+\-@\t\r]/;

export function csvCell(value: Cell): string {
  if (value === null) return "";
  let text = String(value);
  if (typeof value === "string" && FORMULA_START.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: string[], rows: Cell[][]): string {
  const lines = [columns.map(csvCell), ...rows.map((row) => row.map(csvCell))];
  return lines.map((cells) => cells.join(",")).join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, columns: string[], rows: Cell[][]): void {
  const blob = new Blob(["﻿" + toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
