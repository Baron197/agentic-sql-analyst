import { useEffect, useReducer, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { ApiError, api, askStream } from "../api/client";
import type { Example } from "../api/types";
import { RunResult } from "../components/RunResult";
import { emptyRun, runReducer } from "../lib/run";

const MAX_CHARS = 500;

export function AskPage() {
  const [question, setQuestion] = useState("");
  const [run, dispatch] = useReducer(runReducer, emptyRun);
  const [examples, setExamples] = useState<Example[]>([]);
  const [keyless, setKeyless] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const running = run.phase === "running";

  useEffect(() => {
    api
      .examples()
      .then((r) => {
        setExamples(r.examples);
        setKeyless(r.keyless);
      })
      .catch(() => setExamples([]));
    return () => abort.current?.abort();
  }, []);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || running) return;
    abort.current?.abort();
    abort.current = new AbortController();
    dispatch({ type: "start", question: q });
    try {
      await askStream(
        q,
        {
          onStep: (step) => dispatch({ type: "step", step }),
          onSql: (sql) => dispatch({ type: "sql", sql }),
          onRows: (rows) => dispatch({ type: "rows", rows }),
          onAnswer: (answer) => dispatch({ type: "answer", answer }),
          onDone: (done) => dispatch({ type: "done", done }),
          onError: (error) => dispatch({ type: "error", error }),
        },
        abort.current.signal,
      );
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      dispatch({
        type: "error",
        error:
          e instanceof ApiError
            ? { code: e.code, message: e.message }
            : {
                code: "network",
                message: "The connection to the server was lost. Please try again.",
              },
      });
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(question);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask(question);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold sm:text-3xl">Ask the data</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-mute">
          Questions about PT Arunika Niaga&apos;s sales, customers, stores, and operations, in
          English or Bahasa Indonesia. You get the answer, the SQL behind it, and the rows.
        </p>
      </div>

      <form onSubmit={submit} className="card p-3 sm:p-4" aria-label="Ask a question">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          rows={2}
          maxLength={MAX_CHARS}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="e.g. What was net revenue by sales channel in Q1 2026?"
          className="w-full resize-none bg-transparent px-1 text-[15px] text-ink placeholder:text-ink-mute focus:outline-none"
        />
        <div className="mt-2 flex items-center gap-3">
          <span className="text-xs text-ink-mute tabular-nums" aria-live="polite">
            {question.length}/{MAX_CHARS}
          </span>
          <span className="hidden text-xs text-ink-mute sm:inline">
            Enter to ask · Shift+Enter for a new line
          </span>
          <button
            type="submit"
            className="btn-primary ml-auto"
            disabled={running || !question.trim()}
          >
            {running ? "Working…" : "Ask"}
          </button>
        </div>
      </form>

      {examples.length > 0 && (
        <section aria-labelledby="examples-title">
          <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h2 id="examples-title" className="label">
              {keyless ? "Demo questions" : "Try"}
            </h2>
            {keyless && (
              <span className="text-xs text-ink-mute">
                Keyless mode: these questions replay a scripted model; the rest of the pipeline is
                real.
              </span>
            )}
          </div>
          <ul className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <li key={ex.question}>
                <button
                  type="button"
                  disabled={running}
                  onClick={() => {
                    setQuestion(ex.question);
                    void ask(ex.question);
                  }}
                  className="rounded-2xl border border-line px-3 py-1.5 text-left text-sm text-ink-soft sm:rounded-full transition-colors hover:border-line-hover hover:text-ink disabled:opacity-50"
                >
                  {ex.question}
                  {ex.lang === "id" && <span className="ml-1.5 text-xs text-ink-mute">ID</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {run.phase !== "idle" && (
        <section aria-label="Result of your question">
          <p className="mb-3 text-sm text-ink-mute">
            <span className="text-ink-soft">Question:</span> {run.question}
          </p>
          <RunResult
            run={run}
            onAsk={(q) => {
              setQuestion(q);
              void ask(q);
            }}
          />
        </section>
      )}
    </div>
  );
}
