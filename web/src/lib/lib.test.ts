import { describe, expect, it } from "vitest";

import type { RunRecord } from "../api/types";
import { csvCell, toCsv } from "./csv";
import { formatCell, formatUsd, humanize } from "./format";
import { emptyRun, fromRecord, runReducer } from "./run";
import { formatSql } from "./sqlFormat";

describe("CSV export", () => {
  it("quotes commas, quotes, and newlines", () => {
    expect(
      toCsv(
        ["a", "b"],
        [
          ["x,y", 'say "hi"'],
          ["line\nbreak", null],
        ],
      ),
    ).toBe('a,b\r\n"x,y","say ""hi"""\r\n"line\nbreak",\r\n');
  });

  it("neutralises cells a spreadsheet would run as formulas", () => {
    expect(csvCell('=HYPERLINK("http://evil")')).toBe('"\'=HYPERLINK(""http://evil"")"');
    expect(csvCell("+1")).toBe("'+1");
    expect(csvCell("-2")).toBe("'-2");
    expect(csvCell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(csvCell(-2)).toBe("-2"); // real numbers stay numbers
  });
});

describe("formatting", () => {
  it("groups measures but leaves years and ids alone", () => {
    expect(formatCell(1234567.891, "net_revenue_idr")).toBe("1,234,567.891");
    expect(formatCell(2025, "year")).toBe("2025");
    expect(formatCell(1234, "store_id")).toBe("1234");
    expect(formatCell(null)).toBe("NULL");
    expect(formatCell("2025-03-01", "month_start")).toBe("Mar 2025");
    expect(formatCell("2025-05-01T00:00:00+07:00", "bulan")).toBe("May 2025");
    expect(formatCell("2025-03-15", "month")).toBe("2025-03-15"); // not a month start
    expect(formatCell("2025-03-01", "first_order_date")).toBe("2025-03-01"); // not a month column
  });

  it("humanizes column names and formats cost", () => {
    expect(humanize("net_revenue_idr")).toBe("net revenue (IDR)");
    expect(humanize("channel_name")).toBe("channel name");
    expect(formatUsd(0)).toBe("$0");
    expect(formatUsd(0.000412)).toBe("$0.000412");
  });
});

describe("formatSql", () => {
  it("puts main clauses on their own lines, indented inside parentheses", () => {
    const sql =
      "WITH t AS (SELECT a FROM analytics.x AS x WHERE x.b = 'FROM here') SELECT a FROM t ORDER BY a LIMIT 5";
    expect(formatSql(sql)).toBe(
      [
        "WITH t AS (SELECT a",
        "  FROM analytics.x AS x",
        "  WHERE x.b = 'FROM here')",
        "SELECT a",
        "FROM t",
        "ORDER BY a",
        "LIMIT 5",
      ].join("\n"),
    );
  });
});

describe("run state", () => {
  it("follows the stream events", () => {
    let s = runReducer(emptyRun, { type: "start", question: "q" });
    s = runReducer(s, {
      type: "step",
      step: { node: "guard_input", status: "done", ms: 1, note: null },
    });
    s = runReducer(s, { type: "sql", sql: "SELECT 1" });
    expect(s.phase).toBe("running");
    s = runReducer(s, { type: "done", done: { run_id: "r", usage: {} as never } });
    expect(s).toMatchObject({ phase: "done", question: "q", sql: "SELECT 1" });
    expect(s.steps).toHaveLength(1);
    expect(runReducer(s, { type: "start", question: "next" }).steps).toEqual([]);
  });

  it("turns a stored run into the same view", () => {
    const record = {
      run_id: "r1",
      created_at: "2026-10-30T00:00:00Z",
      question: "q",
      status: "answered",
      answer: "a",
      sql: "SELECT 1",
      columns: ["n"],
      rows: [[1]],
      row_count: 1,
      truncated: false,
      chart: { type: "kpi", x: null, y: "n" },
      assumptions: [],
      caveats: [],
      refusal: null,
      repairs: 1,
      model: "m",
      trace: [{ node: "finalize", ms: 2, note: null }],
      usage: {
        llm_calls: 2,
        input_tokens: 10,
        output_tokens: 5,
        cache_read_tokens: 3,
        cache_write_tokens: 2,
        cost_usd: 0.1,
        keyless: false,
      },
      elapsed_ms: 99,
    } satisfies RunRecord;
    const view = fromRecord(record);
    expect(view.phase).toBe("done");
    expect(view.rows?.rows).toEqual([[1]]);
    expect(view.done?.usage).toMatchObject({ input_tokens: 15, repairs: 1, latency_ms: 99 });
  });
});
