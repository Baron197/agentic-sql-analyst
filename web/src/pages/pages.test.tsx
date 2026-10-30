import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth";
import { AskPage } from "./AskPage";
import { LoginPage } from "./LoginPage";

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
