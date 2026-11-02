import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { api } from "../api/client";
import type { RecordedRun } from "../api/types";
import { RunResult } from "../components/RunResult";
import { formatMs, formatUsd } from "../lib/format";
import { STATUS_TONE, fromRecord } from "../lib/run";

// Public pages: real live-model runs recorded in the app and replayed from a file (D048).

const EVAL_RESULTS =
  "https://github.com/Baron197/agentic-sql-analyst/blob/main/docs/EVAL_RESULTS.md";
const LANG_LABEL: Record<string, string> = { en: "English", id: "Bahasa Indonesia" };
const ROLE_LABEL: Record<string, string> = {
  analyst: "analyst, all regions",
  manager: "manager, Jabodetabek only",
};

function useRecordedRuns() {
  const [runs, setRuns] = useState<RecordedRun[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    api
      .recordedRuns()
      .then((r) => setRuns(r.runs))
      .catch(() => setError(true));
  }, []);
  return { runs, error };
}

function LoadState({ runs, error }: { runs: RecordedRun[] | null; error: boolean }) {
  if (error) {
    return (
      <p role="alert" className="text-danger">
        Could not load the recorded runs.
      </p>
    );
  }
  if (!runs) {
    return (
      <p role="status" className="text-ink-mute">
        Loading…
      </p>
    );
  }
  return null;
}

export function RecordedRunsPage() {
  const { runs, error } = useRecordedRuns();
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Recorded runs</h1>
        <p className="max-w-[760px] text-sm text-ink-mute">
          Real answers from the agent with a live model, recorded in this app and replayed from a
          file: opening one makes no model call. They are hand-picked to show how the system
          behaves, refusals included. Measured accuracy is in the{" "}
          <a href={EVAL_RESULTS} className="text-accent hover:underline">
            evaluation results
          </a>
          .
        </p>
      </div>
      <LoadState runs={runs} error={error} />
      {runs?.length === 0 && <p className="text-ink-mute">No runs recorded yet.</p>}
      {runs && runs.length > 0 && (
        <ul className="card divide-y divide-line-faint">
          {runs.map((r) => (
            <li key={r.run_id}>
              <Link
                to={`/recorded/${r.run_id}`}
                className="flex flex-col gap-1 px-4 py-3 transition-colors hover:bg-panel sm:flex-row sm:items-center sm:gap-4"
              >
                <span className="min-w-0 flex-1 truncate text-ink">{r.question}</span>
                <span className="flex shrink-0 items-center gap-3 text-xs text-ink-mute">
                  <span className={STATUS_TONE[r.status]}>{r.status}</span>
                  <span>{LANG_LABEL[r.lang] ?? r.lang}</span>
                  <span className="font-mono">{r.model}</span>
                  <span className="font-mono">{formatMs(r.elapsed_ms)}</span>
                  <span className="font-mono">{formatUsd(r.usage.cost_usd)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RecordedRunPage() {
  const { runId = "" } = useParams();
  const { runs, error } = useRecordedRuns();
  const run = runs?.find((r) => r.run_id === runId);
  return (
    <div className="space-y-4">
      <Link to="/recorded" className="text-sm text-ink-mute hover:text-ink">
        ← Recorded runs
      </Link>
      <LoadState runs={runs} error={error} />
      {runs && !run && (
        <p role="alert" className="text-danger">
          No such recorded run.
        </p>
      )}
      {run && (
        <>
          <h1 className="text-xl font-semibold">{run.question}</h1>
          <p className="text-xs text-ink-mute">
            Recorded live run,{" "}
            {new Date(run.created_at).toLocaleDateString("en-GB", { dateStyle: "medium" })}, asked
            as the {ROLE_LABEL[run.role] ?? run.role}. Replayed from a file: no model call. The
            stored run keeps the first 50 rows.
          </p>
          <RunResult run={fromRecord(run)} />
        </>
      )}
    </div>
  );
}
