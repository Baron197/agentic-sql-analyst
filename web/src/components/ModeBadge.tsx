import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Health } from "../api/types";
import { modeOf } from "../lib/run";

// Which model answers new questions right now, from the public GET /api/health.

const TONE: Record<ReturnType<typeof modeOf>["tone"], string> = {
  live: "border-accent/40 text-accent-soft",
  off: "border-line text-ink-mute",
  keyless: "border-warn/40 text-warn",
};

export function ModeBadge() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null)); // the badge is informative only: hide it on failure
  }, []);
  if (!health) return null;
  const { tone, label, model, title } = modeOf(health);
  return (
    <span className={`chip whitespace-nowrap font-mono ${TONE[tone]}`} title={title}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      <span className="sr-only">Mode: </span>
      {label}
      {model && <span className="max-xl:sr-only">· {model}</span>}
    </span>
  );
}
