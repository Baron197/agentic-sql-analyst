// Thin API client. The session is an httpOnly cookie, so requests only need
// `credentials: "same-origin"`; a 401 tells the app to show the sign-in page.

import { readSSE } from "./sse";
import type {
  AnswerEvent,
  AuthOptions,
  DoneEvent,
  ErrorEvent,
  EvalRun,
  Example,
  Health,
  Me,
  RecordedRun,
  RowsEvent,
  RunRecord,
  RunSummary,
  Schema,
  StepEvent,
} from "./types";

export const SESSION_EXPIRED = "sqla:session-expired";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function toError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `The server answered ${response.status}.`;
  try {
    const body = await response.json();
    if (body?.detail?.code) {
      code = body.detail.code;
      message = body.detail.message;
    } else if (Array.isArray(body?.detail)) {
      code = "invalid_request";
      message = "The request was not valid.";
    }
  } catch {
    // not JSON: keep the generic message
  }
  if (response.status === 401 && code !== "bad_credentials") {
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  return new ApiError(response.status, code, message);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) throw await toError(response);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  me: () => call<Me>("/api/me"),
  health: () => call<Health>("/api/health"),
  authOptions: () => call<AuthOptions>("/api/auth/options"),
  login: (email: string, password: string) => post<Me>("/api/auth/login", { email, password }),
  demoLogin: (user: string) => post<Me>("/api/auth/demo", { user }),
  logout: () => post<void>("/api/auth/logout"),
  examples: () => call<{ keyless: boolean; examples: Example[] }>("/api/examples"),
  schema: () => call<Schema>("/api/schema"),
  runs: (limit = 50) => call<{ runs: RunSummary[] }>(`/api/runs?limit=${limit}`),
  run: (runId: string) => call<RunRecord>(`/api/runs/${encodeURIComponent(runId)}`),
  recordedRuns: () => call<{ runs: RecordedRun[] }>("/api/recorded-runs"),
  evalSummary: () => call<{ runs: EvalRun[] }>("/api/eval-summary"),
};

export interface StreamHandlers {
  onStep: (e: StepEvent) => void;
  onSql: (sql: string) => void;
  onRows: (e: RowsEvent) => void;
  onAnswer: (e: AnswerEvent) => void;
  onDone: (e: DoneEvent) => void;
  onError: (e: ErrorEvent) => void;
}

/** POST /api/ask/stream and dispatch each event. Rejects with ApiError on a non-200 answer. */
export async function askStream(
  question: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/ask/stream", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) throw await toError(response);
  for await (const { event, data } of readSSE(response.body)) {
    const payload = JSON.parse(data);
    switch (event) {
      case "step":
        handlers.onStep(payload);
        break;
      case "sql":
        handlers.onSql(payload.sql);
        break;
      case "rows":
        handlers.onRows(payload);
        break;
      case "answer":
        handlers.onAnswer(payload);
        break;
      case "done":
        handlers.onDone(payload);
        break;
      case "error":
        handlers.onError(payload);
        break;
    }
  }
}
