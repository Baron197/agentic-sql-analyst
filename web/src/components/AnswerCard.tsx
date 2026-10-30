import type { AnswerEvent, ErrorEvent } from "../api/types";

const STATUS: Record<string, { label: string; tone: string }> = {
  answered: { label: "Answer", tone: "border-accent/40" },
  refused: { label: "Not answered", tone: "border-warn/40" },
  partial: { label: "Stopped early", tone: "border-warn/40" },
  error: { label: "Couldn't answer", tone: "border-danger/40" },
};

export function AnswerCard({
  answer,
  error,
  onAsk,
}: {
  answer: AnswerEvent | null;
  error?: ErrorEvent | null;
  onAsk?: (question: string) => void; // makes suggested questions clickable
}) {
  if (error) {
    return (
      <section className={`card border-l-4 p-5 ${STATUS.error.tone}`} role="alert">
        <h2 className="label mb-2">{STATUS.error.label}</h2>
        <p className="text-ink">{error.message}</p>
      </section>
    );
  }
  if (!answer) return null;
  const status = STATUS[answer.status] ?? STATUS.answered;
  return (
    <section className={`card border-l-4 p-5 ${status.tone}`} aria-labelledby="answer-title">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 id="answer-title" className="label">
          {status.label}
        </h2>
        {answer.status === "answered" && (
          <span
            className="chip border-accent/30 text-accent-soft"
            title="The model writes a template; code fills every number from the query result."
          >
            <svg viewBox="0 0 16 16" className="h-3 w-3" aria-hidden="true">
              <path
                d="M3 8.5l3 3 7-7"
                stroke="currentColor"
                strokeWidth="2"
                fill="none"
                strokeLinecap="round"
              />
            </svg>
            Numbers filled from the query result
          </span>
        )}
      </div>
      <p className="text-[17px] leading-relaxed text-ink">{answer.text}</p>
      {answer.refusal_reason && answer.status === "refused" && (
        <p className="mt-2 text-sm text-ink-mute">Reason: {answer.refusal_reason}</p>
      )}
      {answer.suggestions.length > 0 && (
        <div className="mt-4">
          <h3 className="label mb-2 font-sans">You could ask instead</h3>
          <ul className="flex flex-wrap gap-2">
            {answer.suggestions.map((q) => (
              <li key={q}>
                {onAsk ? (
                  <button
                    type="button"
                    onClick={() => onAsk(q)}
                    className="rounded-2xl border border-accent/30 px-3 py-1.5 text-left text-sm text-accent-soft transition-colors hover:border-accent hover:text-ink sm:rounded-full"
                  >
                    {q}
                  </button>
                ) : (
                  <span className="chip">{q}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.assumptions.length > 0 && (
        <div className="mt-4">
          <h3 className="label mb-2 font-sans">Assumptions</h3>
          <ul className="flex flex-wrap gap-2">
            {answer.assumptions.map((a) => (
              <li key={a} className="chip border-accent/20 bg-accent/5 text-ink-soft">
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.caveats.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm text-ink-mute">
          {answer.caveats.map((c) => (
            <li key={c}>· {c}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
