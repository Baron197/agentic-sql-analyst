// Shapes returned by the API (backend/src/sql_analyst/api). Keep in sync with models.py.

export type Cell = string | number | boolean | null;

export interface Me {
  user_id: string;
  display_name: string;
  role: "analyst" | "manager";
  region_ids: number[] | null;
}

export interface AuthOptions {
  demo_login_enabled: boolean;
  demo_users: { key: string; email: string; role: string }[];
}

// GET /api/health (public): the header shows which model answers.
export interface Health {
  status: "ok" | "degraded";
  mode: "live" | "keyless";
  live_mode_enabled: boolean;
  model: string;
}

// GET /api/eval-summary (public): the reported test-split runs (eval/summary.py, D050).
export interface Stat {
  mean: number | null;
  std: number | null;
}

export interface EvalRun {
  file: string;
  date: string;
  commit: string;
  system: string;
  mode: string;
  split: string;
  model: string;
  n_questions: number;
  repeats: number;
  metrics: Record<string, Stat>;
  cost_per_question_usd: Stat;
  cost_new_question_usd: number;
  total_cost_usd: number;
}

export type ChartType = "kpi" | "bar" | "line" | "table";

export interface Chart {
  type: ChartType;
  x: string | null;
  y: string | null;
}

export type RunStatus = "answered" | "refused" | "partial" | "error";

export interface Usage {
  model: string;
  keyless: boolean;
  llm_calls: number;
  input_tokens: number;
  cache_read_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  repairs: number;
}

// Server-sent events from POST /api/ask/stream, in this order:
// step (repeated), sql, rows, answer, done -- or error instead of answer/done.
export interface StepEvent {
  node: string;
  status: "done";
  ms: number;
  note: string | null;
}

export interface RowsEvent {
  columns: string[];
  rows: Cell[][];
  row_count: number;
  truncated: boolean;
}

export interface AnswerEvent {
  status: RunStatus;
  text: string | null;
  assumptions: string[];
  caveats: string[];
  chart: Chart | null;
  refusal_reason: string | null;
  suggestions: string[]; // follow-up questions offered with an "unanswerable" refusal
}

export interface DoneEvent {
  run_id: string;
  usage: Usage;
}

export interface ErrorEvent {
  code: string;
  message: string;
  run_id?: string;
}

export interface Example {
  question: string;
  lang: "en" | "id";
}

export interface RunSummary {
  run_id: string;
  created_at: string;
  status: RunStatus;
  question: string;
  model: string;
  keyless: boolean;
  llm_calls: number;
  cost_usd: number;
  elapsed_ms: number;
}

// The stored AgentResult (GET /api/runs/{id}); only the fields the app shows.
export interface RunRecord {
  run_id: string;
  created_at: string;
  question: string;
  status: RunStatus;
  answer: string | null;
  sql: string | null;
  columns: string[];
  rows: Cell[][];
  row_count: number;
  truncated: boolean;
  chart: Chart | null;
  assumptions: string[];
  caveats: string[];
  refusal: { kind: string; reason: string; source: string } | null;
  suggestions?: string[]; // absent in runs stored before the field existed
  repairs: number;
  model: string;
  trace: { node: string; ms: number; note: string | null }[];
  usage: {
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cache_write_tokens: number;
    cost_usd: number;
    keyless: boolean;
  };
  elapsed_ms: number;
}

/** A real live-model run recorded in the app and published (GET /api/recorded-runs, D048). */
export interface RecordedRun extends RunRecord {
  lang: string;
  role: string;
  provider: string;
}

export interface SchemaColumn {
  name: string;
  type: string;
  description: string;
  examples: string[];
  deprecated: string | null;
}

export interface SchemaView {
  name: string;
  description: string;
  grain: string;
  columns: SchemaColumn[];
}

export interface Schema {
  company: string;
  fictional: boolean;
  data_window: { start: string; end: string; note: string };
  your_scope: { role: string; region_ids: number[] | "all" };
  business_rules: string[];
  views: SchemaView[];
  glossary: { name: string; label: { en: string; id: string }; description: string }[];
}
