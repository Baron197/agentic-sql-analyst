"""Cost guard (safety layer 4): refuse queries whose planned cost is too high.

Runs EXPLAIN (FORMAT JSON), which plans without executing, inside the same scoped
read-only transaction the query will run in. The limit is calibrated against the
glossary metrics and typical analytical queries (docs/SECURITY.md); accidental cross
joins between large views land orders of magnitude above it.
"""

import psycopg

from sql_analyst.safety.errors import CostLimitExceeded


def estimate_cost(conn: psycopg.Connection, sql: str) -> float:
    plan = conn.execute("EXPLAIN (FORMAT JSON) " + sql).fetchone()[0]
    return float(plan[0]["Plan"]["Total Cost"])


def check_cost(conn: psycopg.Connection, sql: str, limit: float) -> float:
    """Return the estimated cost, or raise CostLimitExceeded if it is above `limit`."""
    cost = estimate_cost(conn, sql)
    if cost > limit:
        raise CostLimitExceeded(
            f"The query is too expensive to run (planner cost {cost:,.0f} > limit {limit:,.0f}). "
            "Check for a missing join condition (cross join) or aggregate before joining.",
        )
    return cost
