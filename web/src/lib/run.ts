// State of one question while it streams in, and the labels for the agent's steps.

import type {
  AnswerEvent,
  DoneEvent,
  ErrorEvent,
  Health,
  RowsEvent,
  RunRecord,
  StepEvent,
} from "../api/types";

export const STEP_LABELS: Record<string, string> = {
  guard_input: "Check the question",
  retrieve_context: "Find the relevant tables",
  generate_sql: "Write SQL",
  validate_sql: "Validate the SQL",
  execute: "Run it (read-only, your regions)",
  check_result: "Check the result",
  write_answer: "Write the answer",
  render_numbers: "Fill in the numbers",
  refuse: "Refuse politely",
  budget_stop: "Stop: budget reached",
  finalize: "Finish",
};

export const stepLabel = (node: string) => STEP_LABELS[node] ?? node;

export const STATUS_TONE: Record<string, string> = {
  answered: "text-accent-soft",
  refused: "text-warn",
  partial: "text-warn",
  error: "text-danger",
};

/** How a run was answered: a live model (by name), no call at all, or the keyless stand-in. */
export function runMode(keyless: boolean, model: string, llmCalls: number): string {
  if (keyless) return "Keyless (no model)";
  return llmCalls === 0 ? "Live · no model call" : `Live · ${model}`;
}

export const MODE_TONE = (keyless: boolean) =>
  keyless ? "border-warn/40 text-warn" : "border-accent/40 text-accent-soft";

/** The header badge for GET /api/health: which model answers new questions right now. */
export function modeOf(h: Health): {
  tone: "live" | "off" | "keyless";
  label: string;
  model: string | null; // shown next to the label on wide screens; always in the title
  title: string;
} {
  if (h.mode === "keyless") {
    return {
      tone: "keyless",
      label: "Keyless mode",
      model: null,
      title:
        "No model is called: a rule-based stand-in answers the demo questions. SQL, safety checks, and the database run for real.",
    };
  }
  if (!h.live_mode_enabled) {
    return {
      tone: "off",
      label: "Live off",
      model: h.model,
      title: `Live mode (${h.model}) is switched off: new questions are refused until it is back on.`,
    };
  }
  return {
    tone: "live",
    label: "Live",
    model: h.model,
    title: `New questions are answered by ${h.model}, a paid model, within a daily budget.`,
  };
}

export interface RunView {
  phase: "idle" | "running" | "done" | "error";
  question: string;
  steps: StepEvent[];
  sql: string | null;
  rows: RowsEvent | null;
  answer: AnswerEvent | null;
  done: DoneEvent | null;
  error: ErrorEvent | null;
}

export const emptyRun: RunView = {
  phase: "idle",
  question: "",
  steps: [],
  sql: null,
  rows: null,
  answer: null,
  done: null,
  error: null,
};

export type RunAction =
  | { type: "start"; question: string }
  | { type: "step"; step: StepEvent }
  | { type: "sql"; sql: string }
  | { type: "rows"; rows: RowsEvent }
  | { type: "answer"; answer: AnswerEvent }
  | { type: "done"; done: DoneEvent }
  | { type: "error"; error: ErrorEvent };

export function runReducer(state: RunView, action: RunAction): RunView {
  switch (action.type) {
    case "start":
      return { ...emptyRun, phase: "running", question: action.question };
    case "step":
      return { ...state, steps: [...state.steps, action.step] };
    case "sql":
      return { ...state, sql: action.sql };
    case "rows":
      return { ...state, rows: action.rows };
    case "answer":
      return { ...state, answer: action.answer };
    case "done":
      return { ...state, phase: "done", done: action.done };
    case "error":
      return { ...state, phase: "error", error: action.error };
  }
}

/** A stored run (History page) in the same shape as a streamed one. */
export function fromRecord(r: RunRecord): RunView {
  return {
    phase: r.status === "error" ? "error" : "done",
    question: r.question,
    steps: r.trace.map((t) => ({ node: t.node, status: "done", ms: t.ms, note: t.note })),
    sql: r.sql,
    rows: r.columns.length
      ? { columns: r.columns, rows: r.rows, row_count: r.row_count, truncated: r.truncated }
      : null,
    answer:
      r.status === "error"
        ? null
        : {
            status: r.status,
            text: r.answer,
            assumptions: r.assumptions,
            caveats: r.caveats,
            chart: r.chart,
            refusal_reason: r.refusal?.reason ?? null,
            suggestions: r.suggestions ?? [],
          },
    done: {
      run_id: r.run_id,
      usage: {
        model: r.model,
        keyless: r.usage.keyless,
        llm_calls: r.usage.llm_calls,
        input_tokens: r.usage.input_tokens + r.usage.cache_read_tokens + r.usage.cache_write_tokens,
        cache_read_tokens: r.usage.cache_read_tokens,
        output_tokens: r.usage.output_tokens,
        cost_usd: r.usage.cost_usd,
        latency_ms: r.elapsed_ms,
        repairs: r.repairs,
      },
    },
    error:
      r.status === "error" ? { code: "agent_error", message: r.answer ?? "The run failed." } : null,
  };
}
