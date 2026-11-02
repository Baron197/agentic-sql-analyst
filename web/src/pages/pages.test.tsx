import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth";
import { AboutPage } from "./AboutPage";
import { AskPage } from "./AskPage";
import { EvaluationPage } from "./EvaluationPage";
import { HistoryPage } from "./HistoryPage";
import { LoginPage } from "./LoginPage";
import { RecordedRunPage, RecordedRunsPage } from "./RecordedPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function sse(events: [string, unknown][]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const [event, data] of events) {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      }
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const USAGE = {
  model: "fake-keyless",
  keyless: true,
  llm_calls: 2,
  input_tokens: 6000,
  cache_read_tokens: 0,
  output_tokens: 300,
  cost_usd: 0,
  latency_ms: 120,
  repairs: 0,
};

function mockFetch(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input).split("?")[0];
    const handler = routes[url];
    if (!handler) throw new Error(`unexpected fetch ${url} ${_init?.method ?? "GET"}`);
    return handler();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("AskPage", () => {
  it("streams steps, SQL, the table, and the answer for a demo question", async () => {
    const fetchMock = mockFetch({
      "/api/me": () =>
        json({ user_id: "analyst@demo", display_name: "A", role: "analyst", region_ids: null }),
      "/api/examples": () =>
        json({
          keyless: true,
          examples: [{ question: "How many orders per channel?", lang: "en" }],
        }),
      "/api/ask/stream": () =>
        sse([
          ["step", { node: "guard_input", status: "done", ms: 0.1, note: null }],
          ["step", { node: "generate_sql", status: "done", ms: 3, note: "confidence high" }],
          [
            "sql",
            { sql: "SELECT c.channel_name, COUNT(*) AS orders FROM analytics.fact_orders AS o" },
          ],
          [
            "rows",
            {
              columns: ["channel_name", "orders"],
              rows: [
                ["Website", 4321],
                ["App", 99],
              ],
              row_count: 2,
              truncated: false,
            },
          ],
          [
            "answer",
            {
              status: "answered",
              text: "Website had 4,321 orders.",
              assumptions: ["All statuses."],
              caveats: [],
              chart: { type: "bar", x: "channel_name", y: "orders" },
              refusal_reason: null,
              suggestions: [],
            },
          ],
          ["done", { run_id: "run-1", usage: USAGE }],
        ]),
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthProvider>
          <AskPage />
        </AuthProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "How many orders per channel?" }));

    expect(await screen.findByText("Website had 4,321 orders.")).toBeInTheDocument();
    expect(screen.getByText("Check the question")).toBeInTheDocument();
    expect(screen.getByText("Write SQL")).toBeInTheDocument();
    expect(screen.getByText(/FROM analytics\.fact_orders AS o/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "4,321" })).toBeInTheDocument();
    expect(screen.getByText("Keyless demo")).toBeInTheDocument();
    expect(screen.getByText("All statuses.")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/ask/stream");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      question: "How many orders per channel?",
    });
  });

  it("shows the API's message when a question is refused by a limit", async () => {
    mockFetch({
      "/api/me": () =>
        json({ user_id: "analyst@demo", display_name: "A", role: "analyst", region_ids: null }),
      "/api/examples": () => json({ keyless: false, examples: [] }),
      "/api/ask/stream": () =>
        json(
          {
            detail: {
              code: "rate_limited",
              message: "Too many questions: the limit is 10 per minute.",
            },
          },
          429,
        ),
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthProvider>
          <AskPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Your question"), "How many orders?{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many questions");
  });
});

describe("LoginPage", () => {
  const renderLogin = () =>
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>,
    );

  it("shows the server's message for a wrong password", async () => {
    mockFetch({
      "/api/me": () => json({ detail: { code: "not_signed_in", message: "Sign in first." } }, 401),
      "/api/auth/options": () => json({ demo_login_enabled: false, demo_users: [] }),
      "/api/auth/login": () =>
        json({ detail: { code: "bad_credentials", message: "Wrong email or password." } }, 401),
    });
    const user = userEvent.setup();
    renderLogin();
    await user.type(await screen.findByLabelText("Email"), "analyst@demo");
    await user.type(screen.getByLabelText("Password"), "nope");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
  });

  it("offers one-click demo sign-in only when the API enables it", async () => {
    const users = [{ key: "analyst", email: "analyst@demo", role: "analyst" }];
    mockFetch({
      "/api/me": () => json({ detail: { code: "not_signed_in", message: "" } }, 401),
      "/api/auth/options": () => json({ demo_login_enabled: true, demo_users: users }),
    });
    const { unmount } = renderLogin();
    expect(await screen.findByRole("button", { name: "Try as analyst" })).toBeInTheDocument();
    expect(screen.getByText(/history is visible only in this browser session/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "See recorded live runs without signing in" }),
    ).toHaveAttribute("href", "/recorded");
    unmount();

    mockFetch({
      "/api/me": () => json({ detail: { code: "not_signed_in", message: "" } }, 401),
      "/api/auth/options": () => json({ demo_login_enabled: false, demo_users: users }),
    });
    renderLogin();
    expect(await screen.findByText("analyst@demo")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Try as analyst" })).not.toBeInTheDocument(),
    );
  });
});

describe("Recorded runs (public)", () => {
  const RUN = {
    run_id: "abc123",
    created_at: "2026-11-02T14:05:00+07:00",
    question: "Berapa pendapatan bersih per kanal pada Q1 2026?",
    lang: "id",
    role: "analyst",
    provider: "openai",
    model: "gpt-6-luna",
    status: "answered",
    answer: "Pada Q1 2026, Toko fisik menghasilkan pendapatan bersih tertinggi (IDR 9,29 M).",
    sql: "SELECT channel_name, net_revenue_idr FROM analytics.fact_orders",
    columns: ["channel_name", "net_revenue_idr"],
    rows: [["Toko fisik", 9285162700]],
    row_count: 1,
    truncated: false,
    chart: { type: "table", x: null, y: null },
    assumptions: [],
    caveats: [],
    refusal: null,
    suggestions: [],
    repairs: 0,
    trace: [{ node: "generate_sql", ms: 2100, note: "confidence high" }],
    usage: {
      llm_calls: 2,
      input_tokens: 3000,
      output_tokens: 300,
      cache_read_tokens: 2000,
      cache_write_tokens: 0,
      cost_usd: 0.000512,
      keyless: false,
    },
    elapsed_ms: 6234.5,
  };

  const renderAt = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/recorded" element={<RecordedRunsPage />} />
          <Route path="/recorded/:runId" element={<RecordedRunPage />} />
        </Routes>
      </MemoryRouter>,
    );

  it("lists the recorded runs without signing in", async () => {
    const fetchMock = mockFetch({ "/api/recorded-runs": () => json({ runs: [RUN] }) });
    renderAt("/recorded");
    const link = await screen.findByRole("link", { name: /Berapa pendapatan bersih/ });
    expect(link).toHaveAttribute("href", "/recorded/abc123");
    expect(screen.getByText("gpt-6-luna")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // no /api/me: the page needs no session
  });

  it("replays one run with its answer, SQL, and rows", async () => {
    mockFetch({ "/api/recorded-runs": () => json({ runs: [RUN] }) });
    renderAt("/recorded/abc123");
    expect(await screen.findByRole("heading", { name: RUN.question })).toBeInTheDocument();
    expect(screen.getByText(/no model call/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Answer" })).toHaveTextContent("Toko fisik");
    expect(screen.getByRole("table")).toHaveTextContent("Toko fisik");
  });

  it("says so for an unknown run", async () => {
    mockFetch({ "/api/recorded-runs": () => json({ runs: [] }) });
    renderAt("/recorded/nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("No such recorded run.");
  });
});

describe("HistoryPage", () => {
  it("shows whether each run used a live model or the keyless stand-in", async () => {
    const run = { created_at: "2026-11-02T14:05:00+07:00", status: "answered", elapsed_ms: 900 };
    mockFetch({
      "/api/runs": () =>
        json({
          runs: [
            {
              ...run,
              run_id: "a",
              question: "Live one",
              model: "gpt-6-luna",
              keyless: false,
              llm_calls: 2,
              cost_usd: 0.001185,
            },
            {
              ...run,
              run_id: "b",
              question: "Keyless one",
              model: "fake-keyless",
              keyless: true,
              llm_calls: 3,
              cost_usd: 0,
            },
            {
              ...run,
              run_id: "c",
              question: "Refused by the rules",
              model: "gpt-6-luna",
              keyless: false,
              llm_calls: 0,
              cost_usd: 0,
            },
          ],
        }),
    });
    render(
      <MemoryRouter>
        <HistoryPage />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: /Live one/ })).toHaveTextContent(
      "Live · gpt-6-luna",
    );
    expect(screen.getByRole("link", { name: /Keyless one/ })).toHaveTextContent(
      "Keyless (no model)",
    );
    expect(screen.getByRole("link", { name: /Refused by the rules/ })).toHaveTextContent(
      "Live · no model call",
    );
  });
});

describe("Evaluation and About (public)", () => {
  const stat = (mean: number, std = 0) => ({ mean, std });
  const run = (system: string, exRelabeled: number, typed: number, file: string) => ({
    file,
    date: "2026-11-01",
    commit: "00d528b",
    system,
    mode: "live",
    split: "test",
    model: "gpt-6-luna",
    n_questions: 60,
    repeats: 3,
    metrics: {
      ex_strict: stat(0.6867, 0.0306),
      ex_lenient: stat(0.9133, 0.0231),
      ex_relabeled: stat(exRelabeled, 0.0231),
      valid_sql_rate: stat(0.9867, 0.0115),
      false_refusal_rate: stat(0.0133, 0.0115),
      unsafe_refusal_rate: stat(1),
      safety_block_rate: stat(1),
      grounding_violations: stat(typed, typed ? 1.2 : 0),
      latency_p50_ms: stat(7296.97, 787.97),
      latency_p95_ms: stat(14400, 800),
    },
    cost_per_question_usd: stat(0.000476, 0.000159),
    cost_new_question_usd: 0.000659,
    total_cost_usd: 0.0856,
  });

  it("shows the results from the summary, with each run linked to its result file", async () => {
    const fetchMock = mockFetch({
      "/api/eval-summary": () =>
        json({
          runs: [
            run("agent", 0.9333, 0, "a_n60_r3.json"),
            run("baseline", 0.9533, 48.3, "b_n60_r3.json"),
          ],
        }),
    });
    render(
      <MemoryRouter>
        <EvaluationPage />
      </MemoryRouter>,
    );
    const findings = await screen.findByRole("region", { name: "What the numbers say" });
    expect(findings).toHaveTextContent("the agent 93.3 ± 2.3%");
    expect(findings).toHaveTextContent("baseline with the whole data dictionary 95.3 ± 2.3%");
    expect(findings).toHaveTextContent("the agent 0, the baseline 48.3 ± 1.2");
    expect(findings).toHaveTextContent("Every unsafe request was blocked in every run.");
    expect(screen.getAllByRole("link", { name: "2026-11-01" })[0]).toHaveAttribute(
      "href",
      "https://github.com/Baron197/agentic-sql-analyst/blob/main/eval/results/a_n60_r3.json",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1); // no sign-in needed
  });

  it("links the About page to the source code and the evaluation", () => {
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Source code on GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/Baron197/agentic-sql-analyst",
    );
    expect(screen.getAllByRole("link", { name: "Evaluation results" })[0]).toHaveAttribute(
      "href",
      "/evaluation",
    );
    expect(screen.getByRole("region", { name: "Using the demo" })).toHaveTextContent(
      "Jabodetabek only",
    );
  });
});
