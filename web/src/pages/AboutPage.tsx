import { Link } from "react-router";

import { FictionalNotice } from "../components/Layout";
import { REPO, repoFile } from "../lib/links";
import { STEP_LABELS } from "../lib/run";

// Public (D050): what the app is, how to use the demo, how it works, and where to read more.

const GUARANTEES = [
  {
    title: "Read-only by construction",
    body: "Three independent layers stop any write: an SQL validator that parses every query, a read-only transaction, and a database login with no write privileges. Tests switch off two of them at a time and show the third still blocking.",
  },
  {
    title: "You only see what you're allowed to see",
    body: "Row-level security in Postgres limits every query to your regions, using a signed scope set by the server, never by the model. A regional manager sees zero rows from other regions, even with hand-written SQL.",
  },
  {
    title: "The model never types a number",
    body: "The model writes a template with slots; code fills every figure from the query result and rejects any digit the model typed that isn't in your question.",
  },
  {
    title: "It shows its work",
    body: "Every answer comes with the SQL that ran, the rows, the assumptions it made, and the tokens, cost, and time it took.",
  },
];

const PIPELINE = [
  "guard_input",
  "retrieve_context",
  "generate_sql",
  "validate_sql",
  "execute",
  "check_result",
  "write_answer",
  "render_numbers",
];

const STACK = [
  ["Agent", "LangGraph, with a budget check between every step"],
  ["Models", "OpenAI gpt-6-luna through a provider-agnostic interface (Anthropic adapter too)"],
  ["Retrieval", "pgvector with local fastembed embeddings"],
  ["Database", "Postgres 16: read-only role, row-level security, 22 analytics views"],
  ["API", "FastAPI with server-sent events, signed session cookies, rate and budget limits"],
  ["Web", "React, Vite, Tailwind CSS, Recharts"],
  ["Delivery", "Docker Compose behind Caddy (HTTPS); CI runs lint, tests, and the full stack"],
];

const DOCS = [
  ["Evaluation write-up", "docs/EVAL_RESULTS.md"],
  ["Security: each threat and the test that covers it", "docs/SECURITY.md"],
  ["Design decisions and trade-offs", "docs/DECISIONS.md"],
  ["The synthetic data and how it is generated", "docs/DATA.md"],
  ["Deployment and running costs", "docs/DEPLOYMENT.md"],
];

const linkClass = "text-accent hover:underline";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className="text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function AboutPage() {
  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold sm:text-3xl">How it works</h1>
        <p className="mt-2 text-ink-soft">
          An agentic analyst over the database of PT Arunika Niaga, a fictional Indonesian retailer.
          You ask in English or Bahasa Indonesia; an agent built with LangGraph finds the relevant
          tables, writes SQL, checks and runs it safely, and writes an answer whose numbers come
          from the result.
        </p>
        <p className="mt-3 text-sm">
          <a href={REPO} className={linkClass}>
            Source code on GitHub
          </a>
          <span className="text-ink-mute"> · </span>
          <Link to="/evaluation" className={linkClass}>
            Evaluation results
          </Link>
          <span className="text-ink-mute"> · </span>
          <Link to="/recorded" className={linkClass}>
            Recorded live runs
          </Link>
        </p>
      </div>

      <Section id="using-title" title="Using the demo">
        <ul className="mt-3 space-y-2.5 text-sm text-ink-soft">
          <li>
            <span className="font-medium text-ink">What you can ask.</span> Sales, revenue, orders,
            returns, products and stock, customers, stores and channels, promotions, web sessions,
            and support tickets, from 1 Jan 2024 to 30 Sep 2026. The{" "}
            <Link to="/dictionary" className={linkClass}>
              Data dictionary
            </Link>{" "}
            (after sign-in) lists every view and metric. Ambiguous questions get a stated
            assumption; questions the data can&apos;t answer get a refusal with suggestions.
          </li>
          <li>
            <span className="font-medium text-ink">Two demo accounts.</span> The analyst sees every
            region. The Jakarta manager sees Jabodetabek only: ask both the same question to see
            row-level security at work.
          </li>
          <li>
            <span className="font-medium text-ink">Live or keyless.</span> The badge at the top of
            the page shows which one is on. In live mode a paid model answers any question. In
            keyless mode no model is called: a rule-based stand-in answers only the listed demo
            questions, while the SQL checks, the database, and number rendering still run for real.
          </li>
          <li>
            <span className="font-medium text-ink">Limits.</span> Live questions share a per-minute
            limit and a daily budget across all visitors. If they are used up, try again later, or
            read the{" "}
            <Link to="/recorded" className={linkClass}>
              recorded runs
            </Link>
            .
          </li>
          <li>
            <span className="font-medium text-ink">Your history.</span> Questions are stored. With
            the one-click demo sign-in, History shows only the questions asked in your browser
            session.
          </li>
        </ul>
      </Section>

      <Section id="pipeline-title" title="The steps">
        <ol className="mt-3 grid gap-2 sm:grid-cols-2">
          {PIPELINE.map((node, i) => (
            <li key={node} className="card flex items-center gap-3 px-3 py-2 text-sm">
              <span className="font-mono text-xs text-accent">
                {String(i + 1).padStart(2, "0")}
              </span>
              {STEP_LABELS[node]}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-sm text-ink-mute">
          A failed validation, a database error, or a suspicious result sends the run back to write
          SQL again, at most three times. A budget on model calls, tokens, cost, and time is checked
          between every step.
        </p>
      </Section>

      <Section id="guarantees-title" title="Four guarantees, each backed by tests">
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {GUARANTEES.map((g, i) => (
            <article key={g.title} className="card p-4">
              <h3 className="font-display text-base font-semibold">
                <span className="mr-2 font-mono text-sm text-accent">{i + 1}</span>
                {g.title}
              </h3>
              <p className="mt-1.5 text-sm text-ink-soft">{g.body}</p>
            </article>
          ))}
        </div>
        <p className="mt-3 text-sm text-ink-mute">
          The threat-to-test table is in{" "}
          <a href={repoFile("docs/SECURITY.md")} className={linkClass}>
            SECURITY.md
          </a>
          .
        </p>
      </Section>

      <Section id="results-title" title="How well it works">
        <p className="mt-2 text-sm text-ink-soft">
          On this schema the agent is about as accurate as a single prompt holding the whole data
          dictionary. Its advantage is that you can check it: every figure in its answers is filled
          in by code from the rows. The{" "}
          <Link to="/evaluation" className={linkClass}>
            Evaluation
          </Link>{" "}
          page has the measured accuracy, cost, and speed, null and negative results included.
        </p>
      </Section>

      <Section id="stack-title" title="Built with">
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {STACK.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink-mute">{k}</dt>
              <dd className="text-ink-soft">{v}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section id="docs-title" title="Read more">
        <ul className="mt-2 space-y-1 text-sm">
          {DOCS.map(([text, path]) => (
            <li key={path}>
              <a href={repoFile(path)} className={linkClass}>
                {text}
              </a>
            </li>
          ))}
        </ul>
      </Section>

      <section aria-labelledby="honesty-title" className="card p-4">
        <h2 id="honesty-title" className="text-lg font-semibold">
          What this is, and isn&apos;t
        </h2>
        <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
          <li>
            · A portfolio project built to production standards, not a product with customers.
          </li>
          <li>· All data is synthetic, generated by a deterministic script.</li>
          <li>
            · Keyless runs test the plumbing, not the model: their answers are scripted, so they say
            nothing about accuracy.
          </li>
          <li>
            · Accuracy figures are published only from committed evaluation results, with the date,
            model, number of questions, and repeats.
          </li>
        </ul>
        <FictionalNotice className="mt-3" />
      </section>
    </div>
  );
}
