"""Hybrid retrieval: BM25 + vector similarity fused by reciprocal-rank fusion (RRF).

For a question it returns a compact, ranked context (BUILD_GUIDE §8.2):
- the most relevant views (from view and column chunks), plus the views that the top
  glossary metric uses and any views needed to join the selection together;
- the glossary metrics that match;
- phrases that fuzzily match real values of categorical columns ("Jkt" -> city_code JKT);
- the most similar few-shot examples.

Vectors live in pgvector (`retrieval.chunks`, built by `poe index-build`); unit tests use an
in-memory store with the hashing embedder instead.
"""

import re
from collections import deque
from collections.abc import Sequence
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool
from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz, process

from sql_analyst.agent.state import ExampleHit, RetrievedContext, ValueMatch, ViewHit
from sql_analyst.dictionary.models import Dictionary
from sql_analyst.dictionary.values import ColumnValue
from sql_analyst.retrieval.corpus import STOPWORDS, Chunk, build_chunks, tokenize
from sql_analyst.retrieval.embed import Embedder
from sql_analyst.retrieval.examples import Example

RRF_K = 60
VECTOR_CANDIDATES = 40
VALUE_MIN_SCORE = 88.0
_PHRASE_WORD = re.compile(r"[\w&'-]+")


class IndexNotBuilt(RuntimeError):
    pass


class VectorStore(Protocol):
    def nearest(self, vector: list[float], limit: int) -> list[str]:
        """Chunk ids, most similar first."""


class MemoryVectorStore:
    def __init__(self, ids: list[str], vectors: list[list[float]]):
        self.ids, self.vectors = ids, vectors

    def nearest(self, vector: list[float], limit: int) -> list[str]:
        sims = [sum(a * b for a, b in zip(vector, v, strict=True)) for v in self.vectors]
        order = sorted(range(len(sims)), key=lambda i: -sims[i])
        return [self.ids[i] for i in order[:limit]]


class PgVectorStore:
    """Cosine nearest neighbours in retrieval.chunks, read as the agent's read-only role."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def nearest(self, vector: list[float], limit: int) -> list[str]:
        literal = "[" + ",".join(f"{x:.7f}" for x in vector) + "]"
        with self.pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                "SELECT id FROM retrieval.chunks "
                "ORDER BY embedding OPERATOR(retrieval.<=>) %s::retrieval.vector LIMIT %s",
                (literal, limit),
            ).fetchall()
        return [r[0] for r in rows]


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def _phrase_in_value(phrase: str, value: str, *, processor=None, score_cutoff=None) -> float:
    """How well `phrase` matches all of `value` or a part of it (never the reverse)."""
    if len(phrase) > len(value):
        return fuzz.ratio(phrase, value, score_cutoff=score_cutoff)
    return fuzz.partial_ratio(phrase, value, score_cutoff=score_cutoff)


def match_values(
    question: str, values: list[ColumnValue], limit: int = 8, min_score: float = VALUE_MIN_SCORE
) -> list[ValueMatch]:
    """Phrases (1-4 words) of the question that match a categorical value.

    Phrases of three characters or fewer must match exactly (case-insensitive), so "Jkt"
    finds the city code JKT without "and" matching every short value.
    """
    words = _PHRASE_WORD.findall(question)
    phrases = {" ".join(words[i : i + n]) for n in range(1, 5) for i in range(len(words) - n + 1)}
    choices = [v.value.lower() for v in values]
    best: dict[tuple[str, str, str], ValueMatch] = {}
    for phrase in phrases:
        p = phrase.lower()
        tokens = p.split()
        if all(t in STOPWORDS or t.isdigit() for t in tokens):
            continue
        if len(p) <= 3:
            hits = [(choices[i], 100.0, i) for i, c in enumerate(choices) if c == p]
        else:
            # Multi-word phrases may be part of a longer value ("Gading Serpong" in a store
            # name); single words must match a whole value, or "store" would hit every store.
            scorer = _phrase_in_value if len(tokens) > 1 else fuzz.ratio
            hits = process.extract(p, choices, scorer=scorer, score_cutoff=min_score, limit=5)
        for _choice, score, i in hits:
            v = values[i]
            key = (v.view, v.column, v.value)
            current = best.get(key)
            if current is None or (score, len(phrase)) > (current.score, len(current.phrase)):
                best[key] = ValueMatch(
                    phrase=phrase,
                    view=v.view,
                    column=v.column,
                    value=v.value,
                    score=round(score, 1),
                )
    ranked = sorted(best.values(), key=lambda m: (-m.score, -len(m.phrase), m.view, m.column))
    return ranked[:limit]


class Retriever:
    def __init__(
        self,
        dictionary: Dictionary,
        chunks: list[Chunk],
        values: list[ColumnValue],
        embedder: Embedder,
        vectors: VectorStore,
        *,
        max_views: int = 6,
        max_metrics: int = 3,
        max_examples: int = 4,
        max_values: int = 8,
    ):
        self.dictionary = dictionary
        self.chunks = {c.id: c for c in chunks}
        self.ids = [c.id for c in chunks]
        self.bm25 = BM25Okapi([tokenize(c.text) for c in chunks])
        deprecated = {(v.name, c.name) for v in dictionary.views for c in v.columns if c.deprecated}
        self.values = [v for v in values if (v.view, v.column) not in deprecated]
        self.embedder = embedder
        self.vectors = vectors
        self.max_views, self.max_metrics = max_views, max_metrics
        self.max_examples, self.max_values = max_examples, max_values
        self.join_graph = _join_graph(dictionary)

    # -- construction -----------------------------------------------------------------
    @classmethod
    def in_memory(
        cls,
        dictionary: Dictionary,
        examples: list[Example],
        values: list[ColumnValue],
        embedder: Embedder,
        **kwargs,
    ) -> "Retriever":
        chunks = build_chunks(dictionary, examples)
        store = MemoryVectorStore([c.id for c in chunks], embedder.embed([c.text for c in chunks]))
        return cls(dictionary, chunks, values, embedder, store, **kwargs)

    @classmethod
    def from_db(
        cls, pool: ConnectionPool, dictionary: Dictionary, embedder: Embedder, **kwargs
    ) -> "Retriever":
        """Load the index built by `poe index-build` (read as the agent's read-only role)."""
        try:
            with pool.connection() as conn, conn.transaction():
                meta = dict(conn.execute("SELECT key, value FROM retrieval.meta").fetchall())
                rows = conn.execute(
                    "SELECT id, kind, view_name, content, payload FROM retrieval.chunks ORDER BY id"
                ).fetchall()
                vals = conn.execute(
                    "SELECT view_name, column_name, value, row_count FROM retrieval.column_values"
                ).fetchall()
        except psycopg.Error as e:
            raise IndexNotBuilt(
                "The retrieval index is missing: run `uv run poe index-build`."
            ) from e
        if meta.get("embedding_model") != embedder.name:
            raise IndexNotBuilt(
                f"The index was built with {meta.get('embedding_model')!r} but the agent uses "
                f"{embedder.name!r}: run `uv run poe index-build`."
            )
        chunks = [Chunk(id=i, kind=k, view=v, text=t, payload=p or {}) for i, k, v, t, p in rows]
        values = [ColumnValue(view=v, column=c, value=x, row_count=n) for v, c, x, n in vals]
        return cls(dictionary, chunks, values, embedder, PgVectorStore(pool), **kwargs)

    # -- search -----------------------------------------------------------------------
    def rank(self, question: str) -> list[tuple[str, float]]:
        """All chunks with a fused score, best first."""
        scores = self.bm25.get_scores(tokenize(question))
        lexical = [
            self.ids[i]
            for i in sorted(range(len(scores)), key=lambda i: -scores[i])
            if scores[i] > 0
        ]
        vector = self.vectors.nearest(self.embedder.embed([question])[0], VECTOR_CANDIDATES)
        fused = rrf([lexical, vector])
        return sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))

    def search(self, question: str) -> RetrievedContext:
        ranked = self.rank(question)
        values = match_values(question, self.values, limit=self.max_values)

        view_scores: dict[str, float] = {}
        for cid, score in ranked:
            chunk = self.chunks[cid]
            if chunk.view:
                view_scores[chunk.view] = max(view_scores.get(chunk.view, 0.0), score)
        for m in values:  # a matched value is strong evidence for its view
            view_scores[m.view] = view_scores.get(m.view, 0.0) + 1.0 / (RRF_K + 1)
        top_views = sorted(view_scores, key=lambda v: (-view_scores[v], v))[: self.max_views]

        top_window = {cid for cid, _ in ranked[:15]}
        metrics = [
            cid.removeprefix("metric:")
            for cid, _ in ranked
            if cid.startswith("metric:") and cid in top_window
        ][: self.max_metrics]
        selected = list(top_views)
        if metrics:
            for v in self.chunks[f"metric:{metrics[0]}"].payload.get("views", []):
                if v not in selected:
                    selected.append(v)
        selected = _connect(selected, self.join_graph)

        examples = []
        for cid, score in ranked:
            if cid.startswith("example:") and len(examples) < self.max_examples:
                p = self.chunks[cid].payload
                examples.append(
                    ExampleHit(
                        id=cid.removeprefix("example:"),
                        question=p["question"],
                        decision=p["decision"],
                        sql=p.get("sql"),
                        score=round(score, 5),
                    )
                )
        return RetrievedContext(
            views=[ViewHit(name=v, score=round(view_scores.get(v, 0.0), 5)) for v in selected],
            metrics=metrics,
            values=values,
            examples=examples,
        )


# -- join paths ---------------------------------------------------------------------
def _join_graph(d: Dictionary) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {v.name: set() for v in d.views}
    for j in d.join_paths:
        a, b = j.from_.split(".")[0], j.to.split(".")[0]
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def _distances(graph: dict[str, set[str]], sources: set[str]) -> dict[str, int]:
    dist = {s: 0 for s in sources}
    queue = deque(sources)
    while queue:
        node = queue.popleft()
        for nxt in graph.get(node, ()):
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    return dist


def _bridges(graph: dict[str, set[str]], start: str, targets: set[str]) -> list[str]:
    """Views on any shortest join path from `start` to the targets (both ends excluded).

    All tied paths are kept: fact_orders reaches dim_region through dim_store or dim_customer,
    and which one is right depends on the question (an order's region is its store's).
    """
    from_start, from_targets = _distances(graph, {start}), _distances(graph, targets)
    reachable = [from_start[t] for t in targets if t in from_start]
    if not reachable:
        return []
    d = min(reachable)
    return sorted(
        n
        for n in from_start
        if n != start
        and n not in targets
        and n in from_targets
        and from_start[n] + from_targets[n] == d
    )


def _connect(views: list[str], graph: dict[str, set[str]]) -> list[str]:
    """Add the bridging views needed to join every selected view to the first one."""
    if not views:
        return views
    selected = [views[0]]
    for v in views[1:]:
        if v in selected:
            continue
        for bridge in _bridges(graph, v, set(selected)):
            if bridge not in selected:
                selected.append(bridge)
        selected.append(v)
    return selected
