import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AnswerEvent, RowsEvent } from "../api/types";
import { AnswerCard } from "./AnswerCard";
import { AutoChart } from "./AutoChart";
import { PAGE_SIZE, ResultTable } from "./ResultTable";

const answer = (over: Partial<AnswerEvent> = {}): AnswerEvent => ({
  status: "answered",
  text: "There were 1,234 orders.",
  assumptions: ["All orders, any status."],
  caveats: ["No rows matched the question."],
  chart: null,
  refusal_reason: null,
  suggestions: [],
  ...over,
});

describe("AnswerCard", () => {
  it("shows the answer, the grounding note, assumptions, and caveats", () => {
    render(<AnswerCard answer={answer()} />);
    expect(screen.getByText("There were 1,234 orders.")).toBeInTheDocument();
    expect(screen.getByText("Numbers filled from the query result")).toBeInTheDocument();
    expect(screen.getByText("All orders, any status.")).toBeInTheDocument();
    expect(screen.getByText(/No rows matched/)).toBeInTheDocument();
  });

  it("explains a refusal without claiming the numbers were filled", () => {
    render(
      <AnswerCard
        answer={answer({ status: "refused", refusal_reason: "Asks for personal data." })}
      />,
    );
    expect(screen.getByText("Not answered")).toBeInTheDocument();
    expect(screen.getByText("Reason: Asks for personal data.")).toBeInTheDocument();
    expect(screen.queryByText("Numbers filled from the query result")).not.toBeInTheDocument();
  });

  it("offers follow-up questions with a no-data refusal and asks one when clicked", async () => {
    const asked: string[] = [];
    const user = userEvent.setup();
    render(
      <AnswerCard
        answer={answer({
          status: "refused",
          text: "I can't answer that from the available data.",
          refusal_reason: "The data ends on 30 September 2026.",
          suggestions: ["How many orders in September 2026?"],
          assumptions: [],
          caveats: [],
        })}
        onAsk={(q) => asked.push(q)}
      />,
    );
    await user.click(screen.getByRole("button", { name: "How many orders in September 2026?" }));
    expect(asked).toEqual(["How many orders in September 2026?"]);
  });

  it("shows errors as an alert", () => {
    render(
      <AnswerCard
        answer={null}
        error={{ code: "agent_error", message: "Could not build a query." }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not build a query.");
  });
});

const rows = (n: number): RowsEvent => ({
  columns: ["city", "orders"],
  rows: Array.from({ length: n }, (_, i) => [
    `City ${String(i).padStart(2, "0")}`,
    i === 3 ? null : i * 10,
  ]),
  row_count: n,
  truncated: false,
});

describe("ResultTable", () => {
  it("sorts by a column, NULLs last, and cycles asc → desc → off", async () => {
    const user = userEvent.setup();
    render(<ResultTable result={rows(5)} />);
    const header = screen.getByRole("columnheader", { name: /orders/ });
    const firstCity = () =>
      within(screen.getAllByRole("row")[1]).getAllByRole("cell")[0].textContent;

    await user.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "ascending");
    expect(firstCity()).toBe("City 00");
    await user.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "descending");
    expect(firstCity()).toBe("City 04");
    expect(within(screen.getAllByRole("row")[5]).getAllByRole("cell")[1]).toHaveTextContent("NULL");
    await user.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "none");
  });

  it("paginates long results", async () => {
    const user = userEvent.setup();
    render(<ResultTable result={rows(PAGE_SIZE + 5)} />);
    expect(screen.getAllByRole("row")).toHaveLength(PAGE_SIZE + 1);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getAllByRole("row")).toHaveLength(5 + 1);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("says when there are no rows and when the result was cut off", () => {
    const { rerender } = render(<ResultTable result={{ ...rows(0), row_count: 0 }} />);
    expect(screen.getByText("No rows matched.")).toBeInTheDocument();
    rerender(<ResultTable result={{ ...rows(2), truncated: true }} />);
    expect(screen.getByText("Cut off at the row limit")).toBeInTheDocument();
  });
});

describe("AutoChart", () => {
  const result: RowsEvent = {
    columns: ["month", "orders"],
    rows: [
      ["2025-01-01", 5],
      ["2025-02-01", 7],
    ],
    row_count: 2,
    truncated: false,
  };

  it("shows one number as a KPI", () => {
    render(
      <AutoChart
        chart={{ type: "kpi", x: null, y: "net_revenue_idr" }}
        result={{
          columns: ["net_revenue_idr"],
          rows: [[17_800_000_000]],
          row_count: 1,
          truncated: false,
        }}
      />,
    );
    expect(screen.getByLabelText("Key figure: net_revenue_idr")).toHaveTextContent(
      "17,800,000,000",
    );
  });

  it("labels line and bar charts and renders nothing for tables or unknown columns", () => {
    const { container, rerender } = render(
      <AutoChart chart={{ type: "line", x: "month", y: "orders" }} result={result} />,
    );
    expect(screen.getByLabelText("line chart of orders by month")).toBeInTheDocument();
    rerender(<AutoChart chart={{ type: "table", x: null, y: null }} result={result} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<AutoChart chart={{ type: "bar", x: "city", y: "revenue" }} result={result} />);
    expect(container).toBeEmptyDOMElement();
  });
});
