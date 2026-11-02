import { Suspense, lazy } from "react";

import type { Chart, RowsEvent } from "../api/types";
import { formatCell, humanize } from "../lib/format";

// Recharts is large: load it only when a bar or line chart is needed.
const ChartView = lazy(() => import("./ChartView"));

/** The chart the API chose from the result's shape: one number, bar, line, or none. */
export function AutoChart({ chart, result }: { chart: Chart | null; result: RowsEvent | null }) {
  if (!chart || !result || result.rows.length === 0 || chart.type === "table") return null;
  const yIndex = chart.y ? result.columns.indexOf(chart.y) : -1;
  if (yIndex === -1) return null;

  if (chart.type === "kpi") {
    return (
      <section className="card p-5" aria-label={`Key figure: ${chart.y}`}>
        <p className="label">{humanize(chart.y ?? "")}</p>
        <p className="mt-1 font-display text-4xl font-semibold text-accent-soft tabular-nums">
          {formatCell(result.rows[0][yIndex], chart.y ?? "")}
        </p>
      </section>
    );
  }

  const xIndex = chart.x ? result.columns.indexOf(chart.x) : -1;
  if (xIndex === -1) return null;
  const data = result.rows.map((row) => ({
    x: formatCell(row[xIndex], chart.x ?? ""),
    y: typeof row[yIndex] === "number" ? (row[yIndex] as number) : null,
  }));
  return (
    <section className="card p-4" aria-label={`${chart.type} chart of ${chart.y} by ${chart.x}`}>
      <p className="mb-3 text-sm text-ink-soft">
        {humanize(chart.y ?? "")}{" "}
        <span className="text-ink-mute">by {humanize(chart.x ?? "")}</span>
      </p>
      <Suspense fallback={<div className="h-64" role="status" aria-label="Loading chart" />}>
        <ChartView type={chart.type} data={data} yLabel={chart.y ?? ""} />
      </Suspense>
    </section>
  );
}
