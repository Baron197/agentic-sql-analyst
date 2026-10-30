import { useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import type { Schema } from "../api/types";

export function DictionaryPage() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api
      .schema()
      .then(setSchema)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load the data dictionary."),
      );
  }, []);

  const views = useMemo(() => {
    if (!schema) return [];
    const q = query.trim().toLowerCase();
    if (!q) return schema.views;
    return schema.views
      .map((v) => {
        const viewHit = `${v.name} ${v.description}`.toLowerCase().includes(q);
        const columns = viewHit
          ? v.columns
          : v.columns.filter((c) => `${c.name} ${c.description}`.toLowerCase().includes(q));
        return { ...v, columns };
      })
      .filter((v) => v.columns.length > 0);
  }, [schema, query]);

  if (error)
    return (
      <p role="alert" className="text-danger">
        {error}
      </p>
    );
  if (!schema)
    return (
      <p role="status" className="text-ink-mute">
        Loading…
      </p>
    );

  const scope =
    schema.your_scope.region_ids === "all" ? "all regions" : "the Jabodetabek region only";
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Data dictionary</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-mute">
          The {schema.views.length} views the agent can query (schema{" "}
          <code className="font-mono">analytics</code>
          ), covering {schema.data_window.start} to {schema.data_window.end}. Personal data is not
          in them. Row-level security limits what you see to {scope}.
        </p>
      </div>

      <label className="block max-w-md">
        <span className="sr-only">Search views and columns</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search views and columns (e.g. revenue, store, kategori)"
          className="w-full rounded-[10px] border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-ink-mute focus:border-accent focus:outline-none"
        />
      </label>

      <section aria-labelledby="glossary-title" className="card p-4">
        <h2 id="glossary-title" className="label mb-3">
          Glossary metrics
        </h2>
        <dl className="grid gap-3 sm:grid-cols-2">
          {schema.glossary.map((m) => (
            <div key={m.name}>
              <dt className="text-sm text-ink">
                {m.label.en} <span className="text-ink-mute">/ {m.label.id}</span>
              </dt>
              <dd className="text-xs text-ink-mute">{m.description}</dd>
            </div>
          ))}
        </dl>
      </section>

      {views.length === 0 && <p className="text-ink-mute">Nothing matches “{query}”.</p>}
      <div className="space-y-4">
        {views.map((v) => (
          <section key={v.name} className="card overflow-hidden" aria-labelledby={`view-${v.name}`}>
            <div className="border-b border-line-faint px-4 py-3">
              <h2 id={`view-${v.name}`} className="font-mono text-sm text-accent-soft">
                analytics.{v.name}
              </h2>
              <p className="mt-0.5 text-sm text-ink-soft">{v.description}</p>
              <p className="text-xs text-ink-mute">Grain: {v.grain}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sr-only">
                  <tr>
                    <th scope="col">Column</th>
                    <th scope="col">Type</th>
                    <th scope="col">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {v.columns.map((c) => (
                    <tr key={c.name} className="border-b border-line-faint last:border-0 align-top">
                      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-ink">
                        {c.name}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 font-mono text-xs text-ink-mute">
                        {c.type}
                      </td>
                      <td className="min-w-[16rem] px-4 py-2 text-xs text-ink-soft">
                        {c.description}
                        {c.deprecated && (
                          <span className="ml-1 text-warn">Deprecated: {c.deprecated}</span>
                        )}
                        {c.examples.length > 0 && (
                          <span className="block text-ink-mute">
                            e.g. {c.examples.slice(0, 5).join(", ")}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
