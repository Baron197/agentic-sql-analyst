"""Build the retrieval index in pgvector: `uv run poe index-build`.

Creates the `retrieval` schema (pgvector installed into it) with:
- `chunks`: one row per view, column, glossary metric, and few-shot example, with its embedding;
- `column_values`: distinct values of categorical columns, for fuzzy value matching;
- `meta`: the embedding model and build details.

The agent's read-only role gets SELECT on these tables only. Model-written SQL still
cannot read them: the validator allows analytics views only. The index holds dictionary
text and categorical values (no personal data: no categorical column is flagged pii).
Run it after `db-load`; `db-reset` does both.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable

import psycopg

from sql_analyst.config import READER_ROLE, Settings, get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.dictionary.models import Dictionary
from sql_analyst.dictionary.values import fetch_values
from sql_analyst.retrieval.corpus import build_chunks
from sql_analyst.retrieval.embed import Embedder, make_embedder
from sql_analyst.retrieval.examples import Example, load_examples
from sql_analyst.safety.scope import UserScope, apply_scope

_ALL_REGIONS = UserScope(user_id="index-build", role="analyst", region_ids="all")

DDL = """
DROP EXTENSION IF EXISTS vector CASCADE;
DROP SCHEMA IF EXISTS retrieval CASCADE;
CREATE SCHEMA retrieval;
CREATE EXTENSION vector WITH SCHEMA retrieval;
CREATE TABLE retrieval.meta (key text PRIMARY KEY, value text NOT NULL);
CREATE TABLE retrieval.chunks (
    id text PRIMARY KEY,
    kind text NOT NULL,
    view_name text,
    content text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{{}}',
    embedding retrieval.vector({dim}) NOT NULL
);
CREATE TABLE retrieval.column_values (
    view_name text NOT NULL,
    column_name text NOT NULL,
    value text NOT NULL,
    row_count integer NOT NULL,
    PRIMARY KEY (view_name, column_name, value)
);
"""


def build_index(
    settings: Settings,
    embedder: Embedder,
    dictionary: Dictionary | None = None,
    examples: list[Example] | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    dictionary = dictionary or load_dictionary()
    examples = examples if examples is not None else load_examples()
    chunks = build_chunks(dictionary, examples)
    started = time.perf_counter()
    vectors = embedder.embed([c.text for c in chunks])
    log(
        f"embedded {len(chunks)} chunks with {embedder.name} in {time.perf_counter() - started:.1f} s"
    )

    with psycopg.connect(settings.admin_conninfo()) as conn:
        with conn.transaction():
            apply_scope(conn, _ALL_REGIONS, settings.signing_key())  # analytics views are RLS'd
            values = fetch_values(conn, dictionary)
        with conn.transaction():
            conn.execute(DDL.format(dim=embedder.dim))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO retrieval.chunks (id, kind, view_name, content, payload, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s::retrieval.vector)",
                    [
                        (c.id, c.kind, c.view, c.text, json.dumps(c.payload),
                         "[" + ",".join(f"{x:.7f}" for x in v) + "]")
                        for c, v in zip(chunks, vectors, strict=True)
                    ],
                )  # fmt: skip
                cur.executemany(
                    "INSERT INTO retrieval.column_values VALUES (%s, %s, %s, %s)",
                    [(v.view, v.column, v.value, v.row_count) for v in values],
                )
                cur.executemany(
                    "INSERT INTO retrieval.meta VALUES (%s, %s)",
                    [
                        ("embedding_model", embedder.name),
                        ("dim", str(embedder.dim)),
                        ("chunks", str(len(chunks))),
                        ("values", str(len(values))),
                    ],
                )
            conn.execute(f"GRANT USAGE ON SCHEMA retrieval TO {READER_ROLE}")
            conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA retrieval TO {READER_ROLE}")
    return {"chunks": len(chunks), "values": len(values)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="index-build", description=__doc__)
    p.add_argument(
        "--embedder",
        choices=["fastembed", "hash"],
        default="fastembed",
        help="hash = no model download (tests only; retrieval quality is poor)",
    )
    args = p.parse_args(argv)
    settings = get_settings()
    started = time.perf_counter()
    counts = build_index(settings, make_embedder(settings, args.embedder))
    print(
        f"index-build: {counts['chunks']} chunks, {counts['values']} values "
        f"in {time.perf_counter() - started:.1f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
