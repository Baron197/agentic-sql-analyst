import { useEffect, useState } from "react";
import { Link } from "react-router";

import { api } from "../api/client";
import type { EvalRun, Stat } from "../api/types";
import { formatUsd } from "../lib/format";
import { repoFile } from "../lib/links";

// Public: the reported test-split evaluation (D050). Every number on this page comes from
// data/eval_summary.json, which a test keeps equal to the committed files in eval/results/.

const SYSTEM_LABEL: Record<string, string> = {
  agent: "Agent",
  baseline: "Single-prompt baseline",
  "agent-no-retrieval": "Agent, no retrieval",
  "agent-no-repair": "Agent, no repair",
  "agent-no-few-shot": "Agent, no few-shot examples",
  "agent-critic": "Agent + critic step",
};

const QUALITY: [string, string][] = [
  ["EX strict", "ex_strict"],
  ["EX lenient", "ex_lenient"],
  ["EX relabeled", "ex_relabeled"],
  ["Valid SQL", "valid_sql_rate"],
  ["False refusals", "false_refusal_rate"],
  ["Unsafe refused", "unsafe_refusal_rate"],
];

const TERMS: [string, string][] = [
  [
    "EX strict",
    "Execution accuracy: the rows match the gold query's rows and columns exactly (values compared, column names ignored).",
  ],
  ["EX lenient", "Extra columns are allowed, as long as every gold column is there."],
  [
    "EX relabeled",
    "Lenient, and a label column may use different wording if it maps one-to-one to the gold labels. Cases that pass only this way were checked by hand.",
  ],
  ["Valid SQL", "Answerable questions where the system's SQL passed validation and ran."],
  ["False refusals", "Answerable questions the system refused."],
  [
    "Unsafe refused",
    "Requests to change data, read personal data or raw tables, or follow instructions hidden in the data, that were refused.",
  ],
  [
    "Typed numbers",
    "Answers with a digit the model typed itself instead of code filling it in from the result. Not necessarily wrong, but a reader has to check it.",
  ],
  [
    "±",
    "Standard deviation over the 3 repeats: how much the model varies from run to run, not how much the scores would move on other questions.",
  ],
];

const label = (r: EvalRun) => SYSTEM_LABEL[r.system] ?? r.system;

/** A rate in percent: "93.3 ± 2.3". */
function pct(s: Stat | undefined): string {
  if (!s || s.mean === null) return "n/a";
  const mean = (s.mean * 100).toFixed(1);
  return s.std ? `${mean} ± ${(s.std * 100).toFixed(1)}` : mean;
}

function plain(s: Stat | undefined, scale = 1): string {
  if (!s || s.mean === null) return "n/a";
  const digits = scale === 1 && Number.isInteger(s.mean) && !s.std ? 0 : 1;
  const mean = (s.mean / scale).toFixed(digits);
  return s.std ? `${mean} ± ${(s.std / scale).toFixed(1)}` : mean;
}

const points = (a: Stat, b: Stat) => ((a.mean ?? 0) - (b.mean ?? 0)) * 100;

function FileLink({ run }: { run: EvalRun }) {
  return (
    <a
      href={repoFile(`eval/results/${run.file}`)}
      className="font-mono text-xs text-accent hover:underline"
      title={run.file}
    >
      {run.date}
    </a>
  );
}

function Th({ children, left = false }: { children: React.ReactNode; left?: boolean }) {
  return (
    <th
      scope="col"
      className={`whitespace-nowrap border-b border-line-faint px-3 py-2 text-xs font-medium text-ink-mute ${left ? "text-left" : "text-right"}`}
    >
      {children}
    </th>
  );
}

function Td({ children, left = false }: { children: React.ReactNode; left?: boolean }) {
  return (
    <td
      className={`whitespace-nowrap px-3 py-1.5 ${left ? "text-left text-ink" : "text-right font-mono text-xs tabular-nums text-ink-soft"}`}
    >
      {children}
    </td>
  );
}

function Finding({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="card p-4">
      <h3 className="font-display text-base font-semibold">{title}</h3>
      <p className="mt-1.5 text-sm text-ink-soft">{children}</p>
    </article>
  );
}

function Findings({ runs }: { runs: EvalRun[] }) {
  const agent = runs.find((r) => r.system === "agent");
  const baseline = runs.find((r) => r.system === "baseline" && r.model === agent?.model);
  if (!agent || !baseline) return null;
  const m = agent.metrics;
  const ablations = runs.filter((r) => r.system.startsWith("agent-no-"));
  const critic = runs.find((r) => r.system === "agent-critic");
  const maxGap = Math.max(
    ...ablations.map((r) => Math.abs(points(r.metrics.ex_relabeled, m.ex_relabeled))),
  );
  const allSafe = runs.every((r) => r.metrics.safety_block_rate.mean === 1);
  const onePoint = (100 / agent.n_questions).toFixed(1);
  return (
    <section aria-labelledby="findings-title">
      <h2 id="findings-title" className="text-lg font-semibold">
        What the numbers say
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Finding title="Not more accurate than a single prompt">
          EX relabeled: the agent {pct(m.ex_relabeled)}%, a single-prompt baseline with the whole
          data dictionary {pct(baseline.metrics.ex_relabeled)}%. That is within noise: one question
          is {onePoint} points. This schema is small enough to fit in one prompt.
        </Finding>
        <Finding title="Every figure filled in by code">
          Answers with a number the model typed itself, per run of {agent.n_questions} questions:
          the agent {plain(m.grounding_violations)}, the baseline{" "}
          {plain(baseline.metrics.grounding_violations)}. This is the agent&apos;s real advantage:
          you can check its answers against the rows.
        </Finding>
        <Finding title="Retrieval, repair, few-shot: no measurable gain">
          Switching each off moved EX relabeled by at most {maxGap.toFixed(1)} points: null results,
          published as such.
          {critic && (
            <>
              {" "}
              An extra critic step made it worse ({pct(critic.metrics.ex_relabeled)}%, with false
              refusals up to {pct(critic.metrics.false_refusal_rate)}%), so it stays off.
            </>
          )}
        </Finding>
        <Finding title="Safe, fast enough, and cheap">
          {allSafe && "Every unsafe request was blocked in every run. "}
          The agent took {plain(m.latency_p50_ms, 1000)} s at the median and{" "}
          {plain(m.latency_p95_ms, 1000)} s at p95, and cost{" "}
          {formatUsd(agent.cost_new_question_usd)} for a new question (
          {formatUsd(agent.cost_per_question_usd.mean ?? 0)} on average with the prompt cache).
        </Finding>
      </div>
    </section>
  );
}

export function EvaluationPage() {
  const [runs, setRuns] = useState<EvalRun[] | null>(null);
  const [error, setError] = useState(false);
  const [pricesAsOf, setPricesAsOf] = useState<string | null>(null);
  useEffect(() => {
    api
      .evalSummary()
      .then((r) => {
        setRuns(r.runs);
        setPricesAsOf(r.prices_as_of ?? null);
      })
      .catch(() => setError(true));
  }, []);

  const first = runs?.[0];
  const dates = [...new Set(runs?.map((r) => r.date))].sort();
  return (
    <div className="space-y-8">
      <div className="max-w-3xl space-y-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">Evaluation</h1>
        <p className="text-ink-soft">
          How well the agent answers, measured on a golden set of questions about this fictional
          company, against a single-prompt baseline and with parts of the agent switched off.
        </p>
        {first && (
          <p className="text-sm text-ink-mute">
            Test split: {first.n_questions} questions in English and Bahasa Indonesia, each asked{" "}
            {first.repeats} times per system with live models, from {dates[0]} to{" "}
            {dates[dates.length - 1]}. Test questions were never used for prompts, examples, or
            tuning. Every number here comes from a committed result file (the date links to it); the
            full write-up is in{" "}
            <a href={repoFile("docs/EVAL_RESULTS.md")} className="text-accent hover:underline">
              EVAL_RESULTS.md
            </a>
            . Differences under about 5 points are not meaningful at this size.
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-danger">
          Could not load the evaluation results.
        </p>
      )}
      {!runs && !error && (
        <p role="status" className="text-ink-mute">
          Loading…
        </p>
      )}
      {runs?.length === 0 && <p className="text-ink-mute">No results published yet.</p>}

      {runs && runs.length > 0 && (
        <>
          <Findings runs={runs} />

          <section aria-labelledby="quality-title" className="space-y-3">
            <h2 id="quality-title" className="text-lg font-semibold">
              Quality{" "}
              <span className="text-sm font-normal text-ink-mute">(percent, mean ± std)</span>
            </h2>
            <div className="card overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <Th left>System</Th>
                    <Th left>Model</Th>
                    {QUALITY.map(([name]) => (
                      <Th key={name}>{name}</Th>
                    ))}
                    <Th>Typed numbers</Th>
                    <Th>Result file</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.file} className="odd:bg-panel">
                      <Td left>{label(r)}</Td>
                      <Td left>
                        <span className="font-mono text-xs text-ink-soft">{r.model}</span>
                      </Td>
                      {QUALITY.map(([name, key]) => (
                        <Td key={name}>{pct(r.metrics[key])}</Td>
                      ))}
                      <Td>{plain(r.metrics.grounding_violations)}</Td>
                      <Td>
                        <FileLink run={r} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="speed-title" className="space-y-3">
            <h2 id="speed-title" className="text-lg font-semibold">
              Speed and cost
            </h2>
            <div className="card overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <Th left>System</Th>
                    <Th left>Model</Th>
                    <Th>Median s</Th>
                    <Th>p95 s</Th>
                    <Th>$ per new question</Th>
                    <Th>$ per question (avg)</Th>
                    <Th>Run total</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.file} className="odd:bg-panel">
                      <Td left>{label(r)}</Td>
                      <Td left>
                        <span className="font-mono text-xs text-ink-soft">{r.model}</span>
                      </Td>
                      <Td>{plain(r.metrics.latency_p50_ms, 1000)}</Td>
                      <Td>{plain(r.metrics.latency_p95_ms, 1000)}</Td>
                      <Td>{formatUsd(r.cost_new_question_usd)}</Td>
                      <Td>{formatUsd(r.cost_per_question_usd.mean ?? 0)}</Td>
                      <Td>{formatUsd(r.total_cost_usd)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm text-ink-mute">
              A new question meets a cold prompt cache (the first of the {first?.repeats} repeats);
              the average includes the cheaper repeats, which reuse the cache.
              {pricesAsOf &&
                ` Costs are priced from each run's token counts with the list prices (${pricesAsOf}).`}
            </p>
          </section>

          <section aria-labelledby="terms-title" className="card max-w-3xl p-4">
            <h2 id="terms-title" className="text-lg font-semibold">
              What the scores mean
            </h2>
            <dl className="mt-2 space-y-2 text-sm">
              {TERMS.map(([term, text]) => (
                <div key={term}>
                  <dt className="inline font-medium text-ink">{term}: </dt>
                  <dd className="inline text-ink-soft">{text}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-sm text-ink-mute">
              Answers you can read in full, from the same live model, are on the{" "}
              <Link to="/recorded" className="text-accent hover:underline">
                Recorded runs
              </Link>{" "}
              page.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
