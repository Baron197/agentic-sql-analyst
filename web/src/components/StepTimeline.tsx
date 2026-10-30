import type { StepEvent } from "../api/types";
import { formatMs } from "../lib/format";
import { stepLabel } from "../lib/run";

export function StepTimeline({ steps, running }: { steps: StepEvent[]; running: boolean }) {
  return (
    <section className="card p-4" aria-labelledby="steps-title">
      <h2 id="steps-title" className="label mb-3">
        Steps
      </h2>
      <ol className="space-y-2" aria-live="polite" aria-busy={running}>
        {steps.map((step, i) => (
          <li key={`${step.node}-${i}`} className="flex items-start gap-2.5 text-sm">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="text-ink">{stepLabel(step.node)}</span>
              {step.note && (
                <span className="block truncate text-xs text-ink-mute">{step.note}</span>
              )}
            </span>
            <span className="font-mono text-xs text-ink-mute tabular-nums">
              {formatMs(step.ms)}
            </span>
          </li>
        ))}
        {running && (
          <li className="flex items-center gap-2.5 text-sm text-ink-mute">
            <span
              className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-accent-soft"
              aria-hidden="true"
            />
            Working…
          </li>
        )}
      </ol>
    </section>
  );
}
