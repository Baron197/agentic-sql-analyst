"""retrieve_context, and how the retrieved context is written into the SQL prompt."""

from typing import Any

from sql_analyst.agent.deps import AgentDeps
from sql_analyst.agent.state import AgentState, RetrievedContext
from sql_analyst.dictionary.render import render_join_paths, render_views


def retrieve_context(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    if not deps.config.retrieval or deps.retriever is None:
        return {"context": RetrievedContext(full_schema=True), "_note": "full schema (ablation)"}
    ctx = deps.retriever.search(state.question)
    if not deps.config.few_shot:
        ctx = ctx.model_copy(update={"examples": []})
    note = f"{len(ctx.views)} views, {len(ctx.values)} values, {len(ctx.examples)} examples"
    return {"context": ctx, "_note": note}


def render_context(ctx: RetrievedContext, deps: AgentDeps) -> str:
    """The question-specific part of the SQL prompt (after the cached static part)."""
    parts = []
    if not ctx.full_schema:
        names = [v.name for v in ctx.views]
        parts += ["## Relevant views", render_views(deps.dictionary, names)]
        joins = render_join_paths(deps.dictionary, names)
        if joins:
            parts += ["## Join paths between these views", joins]
    if ctx.metrics:
        parts.append(
            "## Glossary metrics that may apply: "
            + ", ".join(ctx.metrics)
            + " (canonical SQL above)"
        )
    if ctx.values:
        parts.append("## Possible value matches (hints)")
        parts += [
            f"- \"{m.phrase}\" may mean {m.view}.{m.column} = '{m.value}'" for m in ctx.values
        ]
    if ctx.examples:
        parts.append("## Similar solved examples")
        for e in ctx.examples:
            if e.sql:
                parts.append(f"Q: {e.question}\nSQL:\n{e.sql.strip()}")
            else:
                parts.append(f"Q: {e.question}\n-> decision={e.decision}")
    return "\n\n".join(parts)
