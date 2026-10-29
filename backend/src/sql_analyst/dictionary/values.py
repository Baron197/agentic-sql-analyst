"""Value-index source: distinct values of every categorical column in the dictionary.

Phase 4 embeds these so that "Jkt", "Jabodetabek", or "kategori elektronik" can be
matched to real values. Here we only extract them from the database.
"""

import psycopg
from psycopg import sql
from pydantic import BaseModel

from sql_analyst.dictionary.models import Dictionary

MAX_VALUES_PER_COLUMN = 300


class ColumnValue(BaseModel):
    view: str
    column: str
    value: str
    row_count: int


def fetch_values(conn: psycopg.Connection, dictionary: Dictionary) -> list[ColumnValue]:
    """Distinct non-null values per categorical column, most frequent first."""
    out: list[ColumnValue] = []
    for view, column in dictionary.categorical_columns():
        query = sql.SQL(
            "SELECT {col}::text, count(*) FROM analytics.{view} WHERE {col} IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {limit}"
        ).format(
            col=sql.Identifier(column),
            view=sql.Identifier(view),
            limit=sql.Literal(MAX_VALUES_PER_COLUMN + 1),
        )
        for value, n in conn.execute(query):
            out.append(ColumnValue(view=view, column=column, value=value, row_count=n))
    return out
