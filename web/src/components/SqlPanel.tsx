import { useState } from "react";

import { formatSql } from "../lib/sqlFormat";

export function SqlPanel({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <section className="card overflow-hidden" aria-labelledby="sql-title">
      <div className="flex items-center justify-between border-b border-line-faint px-4 py-2.5">
        <h2 id="sql-title" className="label">
          SQL{" "}
          <span className="normal-case tracking-normal">· validated, run as a read-only role</span>
        </h2>
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => void copy()}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="max-h-80 overflow-auto p-4 font-mono text-[13px] leading-relaxed text-ink-soft">
        <code>{formatSql(sql)}</code>
      </pre>
    </section>
  );
}
