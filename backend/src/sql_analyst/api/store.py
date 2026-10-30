"""The API's Postgres store (schema `app`), used through the write-only `app_writer` role.

It reads users, appends runs, and answers the run history, spend, and metrics queries.
It never touches the analytics data: that is the agent's read-only role's job.
"""

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from sql_analyst.safety.scope import UserScope

# The business day is WIB, like the data: "today" starts at midnight Asia/Jakarta.
_TODAY_WIB = "created_at >= (date_trunc('day', now() AT TIME ZONE 'Asia/Jakarta') AT TIME ZONE 'Asia/Jakarta')"


class StoredUser(BaseModel):
    user_id: str
    display_name: str
    password_hash: str
    role: str
    region_ids: list[int] | None

    def scope(self) -> UserScope:
        return UserScope(
            user_id=self.user_id,
            role=self.role,  # type: ignore[arg-type]
            region_ids=self.region_ids if self.region_ids else "all",
        )


class AppStore:
    def __init__(self, conninfo: str, pool_size: int = 4):
        self.pool = ConnectionPool(
            conninfo,
            min_size=1,
            max_size=pool_size,
            open=True,
            timeout=10,
            kwargs={"autocommit": True},
        )

    def close(self) -> None:
        self.pool.close()

    # -- users ----------------------------------------------------------------------
    def user(self, user_id: str) -> StoredUser | None:
        with self.pool.connection() as conn:
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT user_id, display_name, password_hash, role, region_ids "
                    "FROM app.users WHERE user_id = %s",
                    (user_id,),
                )
                .fetchone()
            )
        return StoredUser(**row) if row else None

    # -- runs (RunSink for the agent's finalize node) ---------------------------------
    def save(self, record: dict[str, Any]) -> None:
        u = record["usage"]
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO app.runs (run_id, user_id, status, question, provider, model, keyless, "
                "llm_calls, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
                "cost_usd, elapsed_ms, record) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record["run_id"], record["user_id"], record["status"], record["question"],
                    record["provider"], record["model"], u["keyless"], u["llm_calls"],
                    u["input_tokens"], u["output_tokens"], u["cache_read_tokens"],
                    u["cache_write_tokens"], u["cost_usd"], record["elapsed_ms"], Jsonb(record),
                ),
            )  # fmt: skip

    def runs(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            return (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT run_id, created_at, status, question, model, keyless, cost_usd::float, "
                    "elapsed_ms FROM app.runs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit),
                )
                .fetchall()
            )

    def run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        """A run's full record, only if it belongs to `user_id`."""
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT record FROM app.runs WHERE run_id = %s AND user_id = %s",
                (run_id, user_id),
            ).fetchone()
        return row[0] if row else None

    # -- spend and metrics --------------------------------------------------------------
    def spent_today_usd(self) -> float:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT coalesce(sum(cost_usd), 0)::float FROM app.runs WHERE {_TODAY_WIB}"
            ).fetchone()
        return float(row[0])

    def metrics(self) -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    f"""
                SELECT count(*) AS runs,
                       count(*) FILTER (WHERE status IN ('error', 'partial')) AS failed_runs,
                       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY elapsed_ms)::numeric, 1)::float
                           AS latency_p50_ms,
                       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms)::numeric, 1)::float
                           AS latency_p95_ms,
                       coalesce(sum(cost_usd) FILTER (WHERE {_TODAY_WIB}), 0)::float AS cost_today_usd,
                       count(*) FILTER (WHERE {_TODAY_WIB}) AS runs_today,
                       coalesce(sum(cache_read_tokens), 0) AS cache_read_tokens,
                       coalesce(sum(input_tokens + cache_read_tokens + cache_write_tokens), 0)
                           AS input_tokens_total,
                       count(*) FILTER (WHERE keyless) AS keyless_runs
                FROM app.runs
                """
                )
                .fetchone()
            )
        runs = row["runs"]
        row["error_rate"] = round(row["failed_runs"] / runs, 4) if runs else None
        total_in = row.pop("input_tokens_total")
        row["cache_hit_rate"] = round(row["cache_read_tokens"] / total_in, 4) if total_in else None
        return row
