import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError, api } from "../api/client";
import type { RunSummary } from "../api/types";
import { RunResult } from "../components/RunResult";
import { formatMs, formatUsd } from "../lib/format";
import { MODE_TONE, STATUS_TONE, fromRecord, runMode } from "../lib/run";
import type { RunView } from "../lib/run";

export function HistoryPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then((r) => setRuns(r.runs))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your history."));
  }, []);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">History</h1>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {!runs && !error && (
        <p role="status" className="text-ink-mute">
          Loading…
        </p>
      )}
      {runs?.length === 0 && (
        <p className="text-ink-mute">
          No questions yet.{" "}
          <Link to="/" className="text-accent hover:underline">
            Ask one
          </Link>
          .
        </p>
      )}
      {runs && runs.length > 0 && (
        <ul className="card divide-y divide-line-faint">
          {runs.map((r) => (
            <li key={r.run_id}>
              <Link
                to={`/history/${r.run_id}`}
                className="flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-panel sm:flex-row sm:items-center sm:gap-4"
              >
                <span className="min-w-0 flex-1 truncate text-ink">{r.question}</span>
                <span className="flex shrink-0 items-center gap-3 text-xs text-ink-mute">
                  <span className={STATUS_TONE[r.status]}>{r.status}</span>
                  <span className={`chip px-2 py-0 font-mono ${MODE_TONE(r.keyless)}`}>
                    {runMode(r.keyless, r.model, r.llm_calls)}
                  </span>
                  <span>
                    {new Date(r.created_at).toLocaleString("en-GB", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </span>
                  <span className="font-mono">{formatMs(r.elapsed_ms)}</span>
                  <span className="font-mono">{formatUsd(r.cost_usd)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RunPage() {
  const { runId = "" } = useParams();
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .run(runId)
      .then((r) => setRun(fromRecord(r)))
      .catch((e) =>
        setError(
          e instanceof ApiError && e.status === 404 ? "No such run." : "Could not load the run.",
        ),
      );
  }, [runId]);

  return (
    <div className="space-y-4">
      <Link to="/history" className="text-sm text-ink-mute hover:text-ink">
        ← History
      </Link>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {!run && !error && (
        <p role="status" className="text-ink-mute">
          Loading…
        </p>
      )}
      {run && (
        <>
          <h1 className="text-xl font-semibold">{run.question}</h1>
          <p className="text-xs text-ink-mute">The stored run keeps the first 50 rows.</p>
          <RunResult run={run} />
        </>
      )}
    </div>
  );
}
