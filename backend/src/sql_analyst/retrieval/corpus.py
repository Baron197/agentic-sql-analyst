"""The retrieval corpus: one chunk per view, column, glossary metric, and few-shot example."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from sql_analyst.dictionary.models import Dictionary
from sql_analyst.retrieval.examples import Example

ChunkKind = Literal["view", "column", "metric", "example"]

_WORD = re.compile(r"\w+")
STOPWORDS = frozenset(
    """a an the of in on at to for by and or is are was were be been do does did what which
    who whom how many much when where why show me give list our we us all each per with
    from that this these those it its as into than then there their please apa yang di
    dan atau untuk pada ke dari dengan ini itu ada adalah berapa bagaimana mana siapa
    kapan tolong tampilkan berikan sebutkan saja per oleh dalam""".split()  # noqa: SIM905 (a word list reads better as text)
)


class Chunk(BaseModel):
    id: str
    kind: ChunkKind
    view: str | None = None  # the view a view/column chunk belongs to
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stopwords; snake_case names also split into words."""
    out = []
    for token in _WORD.findall(text.lower()):
        parts = [token, *token.split("_")] if "_" in token else [token]
        out += [p for p in parts if p and p not in STOPWORDS]
    return out


def _words(name: str) -> str:
    return f"{name} {name.replace('_', ' ')}"


def build_chunks(dictionary: Dictionary, examples: list[Example]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for v in dictionary.views:
        chunks.append(
            Chunk(
                id=f"view:{v.name}",
                kind="view",
                view=v.name,
                text=f"{_words(v.name)}. {v.description} Grain: {v.grain}. "
                + ", ".join(v.synonyms.all()),
            )
        )
        for c in v.columns:
            parts = [f"{_words(v.name)} {_words(c.name)}: {c.description}"]
            if c.synonyms.all():
                parts.append("Also called " + ", ".join(c.synonyms.all()) + ".")
            if c.examples:
                parts.append("Values: " + ", ".join(c.examples) + ".")
            chunks.append(
                Chunk(
                    id=f"column:{v.name}.{c.name}", kind="column", view=v.name, text=" ".join(parts)
                )
            )
    for m in dictionary.glossary:
        chunks.append(
            Chunk(
                id=f"metric:{m.name}",
                kind="metric",
                text=f"{_words(m.name)}. {m.label.en} / {m.label.id}: {m.description} "
                + ", ".join(m.synonyms.all()),
                payload={"views": sorted(set(re.findall(r"analytics\.(\w+)", m.sql)))},
            )
        )
    for e in examples:
        chunks.append(
            Chunk(
                id=f"example:{e.id}",
                kind="example",
                text=e.question,
                payload={"question": e.question, "decision": e.decision, "sql": e.sql},
            )
        )
    return chunks
