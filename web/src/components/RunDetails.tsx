import type { DoneEvent } from "../api/types";
import { formatMs, formatUsd } from "../lib/format";

export function RunDetails({ done }: { done: DoneEvent }) {
  const u = done.usage;
  const rows: [string, string][] = [
    ["Mode", u.keyless ? "Keyless (no model)" : u.llm_calls ? "Live model" : "Live, no model call"],
    ["Model", u.model],
    ["LLM calls", String(u.llm_calls)],
    [
      "Input tokens",
      `${u.input_tokens.toLocaleString("en-US")} (${u.cache_read_tokens.toLocaleString("en-US")} cached)`,
    ],
    ["Output tokens", u.output_tokens.toLocaleString("en-US")],
    ["Cost", formatUsd(u.cost_usd)],
    ["Latency", formatMs(u.latency_ms)],
    ["SQL repairs", String(u.repairs)],
  ];
  return (
    <section className="card p-4" aria-labelledby="details-title">
      <div className="mb-3 flex items-center gap-2">
        <h2 id="details-title" className="label">
          Run details
        </h2>
        {u.keyless && (
          <span
            className="chip border-warn/40 text-warn"
            title="Keyless mode: a rule-based stand-in replays a demo answer; everything else ran for real."
          >
            Keyless demo
          </span>
        )}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-mute">{k}</dt>
            <dd className="text-right font-mono text-xs leading-5 text-ink-soft tabular-nums">
              {v}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 truncate font-mono text-[11px] text-ink-mute" title={done.run_id}>
        run {done.run_id}
      </p>
    </section>
  );
}
