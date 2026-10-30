import type { RunView } from "../lib/run";
import { AnswerCard } from "./AnswerCard";
import { AutoChart } from "./AutoChart";
import { ResultTable } from "./ResultTable";
import { RunDetails } from "./RunDetails";
import { SqlPanel } from "./SqlPanel";
import { StepTimeline } from "./StepTimeline";

/** Everything about one run: answer, chart, SQL, rows, steps, and usage. */
export function RunResult({ run }: { run: RunView }) {
  const running = run.phase === "running";
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-5">
        <AnswerCard answer={run.answer} error={run.error} />
        {run.answer && <AutoChart chart={run.answer.chart} result={run.rows} />}
        {run.sql && <SqlPanel sql={run.sql} />}
        {run.rows && (
          <ResultTable result={run.rows} filename={`arunika-${run.done?.run_id ?? "result"}.csv`} />
        )}
      </div>
      {/* On a phone the steps come first while the run is going, then move below the answer. */}
      <aside
        className={`space-y-5 lg:sticky lg:top-24 lg:order-none lg:self-start ${running ? "order-first" : ""}`}
      >
        <StepTimeline steps={run.steps} running={running} />
        {run.done && <RunDetails done={run.done} />}
      </aside>
    </div>
  );
}
