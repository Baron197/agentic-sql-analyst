import { useMemo, useState } from "react";

import type { Cell, RowsEvent } from "../api/types";
import { downloadCsv } from "../lib/csv";
import { formatCell, isNumeric } from "../lib/format";

export const PAGE_SIZE = 25;

type Sort = { column: number; dir: "asc" | "desc" } | null;

function compare(a: Cell, b: Cell, dir: "asc" | "desc"): number {
  if (a === b) return 0;
  if (a === null) return 1; // NULLs last in both directions
  if (b === null) return -1;
  const order =
    typeof a === "number" && typeof b === "number"
      ? a - b
      : String(a).localeCompare(String(b), "en", { numeric: true });
  return dir === "asc" ? order : -order;
}

export function ResultTable({
  result,
  filename = "result.csv",
}: {
  result: RowsEvent;
  filename?: string;
}) {
  const [sort, setSort] = useState<Sort>(null);
  const [page, setPage] = useState(0);
  const { columns, rows } = result;

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const copy = [...rows];
    copy.sort((a, b) => compare(a[sort.column], b[sort.column], sort.dir));
    return copy;
  }, [rows, sort]);

  const pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = sorted.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);
  const numeric = columns.map((_, j) => rows.some((r) => isNumeric(r[j])));

  const toggle = (column: number) => {
    setPage(0);
    setSort((s) =>
      s?.column !== column
        ? { column, dir: "asc" }
        : s.dir === "asc"
          ? { column, dir: "desc" }
          : null,
    );
  };

  return (
    <section className="card overflow-hidden" aria-labelledby="table-title">
      <div className="flex flex-wrap items-center gap-3 border-b border-line-faint px-4 py-2.5">
        <h2 id="table-title" className="label">
          Result{" "}
          <span className="normal-case tracking-normal">
            · {result.row_count.toLocaleString("en-US")} rows
          </span>
        </h2>
        {result.truncated && (
          <span className="chip border-warn/40 text-warn">Cut off at the row limit</span>
        )}
        <button
          type="button"
          className="btn-ghost ml-auto px-2.5 py-1 text-xs"
          onClick={() => downloadCsv(filename, columns, sorted)}
          disabled={rows.length === 0}
        >
          Download CSV
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-sm text-ink-mute">No rows matched.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {columns.map((c, j) => {
                  const dir = sort?.column === j ? sort.dir : null;
                  return (
                    <th
                      key={c}
                      scope="col"
                      aria-sort={
                        dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none"
                      }
                      className={`border-b border-line-faint px-4 py-2 font-medium text-ink-mute ${numeric[j] ? "text-right" : "text-left"}`}
                    >
                      <button
                        type="button"
                        onClick={() => toggle(j)}
                        className="inline-flex items-center gap-1 font-mono text-xs hover:text-ink"
                      >
                        {c}
                        <span aria-hidden="true" className="w-2 text-accent">
                          {dir === "asc" ? "↑" : dir === "desc" ? "↓" : ""}
                        </span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {visible.map((row, i) => (
                <tr key={current * PAGE_SIZE + i} className="odd:bg-panel">
                  {row.map((value, j) => (
                    <td
                      key={columns[j]}
                      className={`whitespace-nowrap px-4 py-1.5 ${numeric[j] ? "text-right font-mono tabular-nums" : ""} ${value === null ? "text-ink-mute" : "text-ink-soft"}`}
                    >
                      {formatCell(value, columns[j])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <nav
          aria-label="Result pages"
          className="flex items-center justify-end gap-2 border-t border-line-faint px-4 py-2 text-xs text-ink-mute"
        >
          <button
            type="button"
            className="btn-ghost px-2.5 py-1 text-xs"
            onClick={() => setPage(current - 1)}
            disabled={current === 0}
          >
            Previous
          </button>
          <span>
            Page {current + 1} of {pages}
          </span>
          <button
            type="button"
            className="btn-ghost px-2.5 py-1 text-xs"
            onClick={() => setPage(current + 1)}
            disabled={current >= pages - 1}
          >
            Next
          </button>
        </nav>
      )}
    </section>
  );
}
