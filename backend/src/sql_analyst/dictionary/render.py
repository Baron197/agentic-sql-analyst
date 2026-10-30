"""Render the semantic layer as compact prompt text.

`render_dictionary` is the whole dictionary (the baseline's prompt and the agent's
no-retrieval ablation). The agent's normal prompt is `render_static` (rules + glossary,
identical for every question so it caches) plus `render_views` for the retrieved views.
"""

from collections.abc import Iterable

from sql_analyst.dictionary.models import Dictionary, View


def render_rules(d: Dictionary) -> str:
    out = [
        f"Company: {d.company}",
        f"Data window: {d.data_window.start} to {d.data_window.end}. {d.data_window.note}",
        "\nBusiness rules:",
    ]
    out += [f"- {r}" for r in d.business_rules]
    return "\n".join(out)


def render_glossary(d: Dictionary) -> str:
    out = ["Glossary metrics (canonical SQL):"]
    for m in d.glossary:
        out.append(
            f"\n### {m.name} ({m.label.en} / {m.label.id}): {m.description}\n{m.sql.strip()}"
        )
    return "\n".join(out)


def render_view(v: View) -> str:
    syn = ", ".join(v.synonyms.all())
    out = [f"## analytics.{v.name}: {v.description} Grain: {v.grain}. Also called: {syn}."]
    for c in v.columns:
        extra = []
        if c.examples:
            extra.append("values e.g. " + ", ".join(c.examples))
        if c.synonyms.all():
            extra.append("aka " + ", ".join(c.synonyms.all()))
        if c.deprecated:
            extra.append("DEPRECATED: " + c.deprecated)
        tail = f" ({'; '.join(extra)})" if extra else ""
        out.append(f"- {c.name} {c.type}: {c.description}{tail}")
    return "\n".join(out)


def render_views(d: Dictionary, names: Iterable[str]) -> str:
    wanted = set(names)
    return "\n\n".join(render_view(v) for v in d.views if v.name in wanted)


def render_join_paths(d: Dictionary, views: Iterable[str] | None = None) -> str:
    """Join paths, limited to those between `views` when given."""
    keep = set(views) if views is not None else None
    lines = []
    for j in d.join_paths:
        ends = {j.from_.split(".")[0], j.to.split(".")[0]}
        if keep is None or ends <= keep:
            lines.append(f"- {j.from_} = {j.to}" + (f" ({j.note})" if j.note else ""))
    return "\n".join(lines)


def render_dictionary(d: Dictionary) -> str:
    """The whole semantic layer as compact text: rules, views, columns, joins, glossary."""
    return "\n".join(
        [
            render_rules(d),
            "\nViews (schema analytics):\n",
            "\n\n".join(render_view(v) for v in d.views),
            "\nJoin paths:",
            render_join_paths(d),
            "",
            render_glossary(d),
        ]
    )


def render_static(d: Dictionary) -> str:
    """Rules + glossary: the part of the agent's SQL prompt that never changes."""
    return render_rules(d) + "\n\n" + render_glossary(d)
