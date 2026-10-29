"""Safety layers 3-5 through the executor: row cap, cost guard, timeout, read-only role."""

import pytest

from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.errors import CostLimitExceeded, QueryFailed, QueryTimeout, SQLRejected
from sql_analyst.safety.executor import Executor
from sql_analyst.safety.validator import SQLValidator

from .conftest import ANALYST, MANAGER
from .test_validator import ALLOWED

pytestmark = pytest.mark.db

CROSS_JOINS = [
    "SELECT count(*) FROM analytics.fact_orders, analytics.fact_order_items",
    "SELECT count(*) FROM analytics.fact_web_sessions s JOIN analytics.dim_customer c ON true",
    "SELECT sum(oi.quantity) FROM analytics.fact_order_items oi JOIN analytics.fact_returns r ON r.quantity > 0",
    "SELECT count(*) FROM analytics.dim_date d, analytics.fact_orders o",
    "SELECT count(*) FROM analytics.fact_inventory_daily i, analytics.dim_store s",
]


@pytest.mark.parametrize("scope", [ANALYST, MANAGER], ids=["analyst", "manager"])
@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_sql_runs_for_both_roles(executor, sql, scope):
    result = executor.run(sql, scope)
    assert result.columns
    assert result.plan_cost <= executor.cost_limit


def test_glossary_values_match_for_the_analyst(executor):
    values = {m.name: executor.run(m.sql, ANALYST).rows[0][0] for m in load_dictionary().glossary}
    assert values["gross_sales"] > values["net_revenue"] > 0


def test_row_cap_truncates_and_reports_it(executor):
    result = executor.run("SELECT order_id FROM analytics.fact_orders", ANALYST)
    assert result.row_count == executor.row_limit == 1000
    assert result.truncated is True
    small = executor.run("SELECT store_id FROM analytics.dim_store", ANALYST)
    assert small.row_count == 40 and small.truncated is False


@pytest.mark.parametrize("sql", CROSS_JOINS)
def test_cost_guard_rejects_cross_joins(executor, sql):
    with pytest.raises(CostLimitExceeded):
        executor.run(sql, ANALYST)


def test_huge_generate_series_is_stopped_by_the_cost_guard(executor):
    with pytest.raises(CostLimitExceeded):
        executor.run("SELECT count(*) FROM generate_series(1, 2000000000) AS g", ANALYST)


def test_statement_timeout_cancels_slow_queries(settings):
    """A recursive CTE looks cheap to the planner but runs long: the timeout stops it."""
    slow = (
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 500000000) "
        "SELECT count(*) FROM r"
    )
    validator = SQLValidator(load_dictionary())
    with (
        Executor(
            validator, settings.reader_conninfo(), settings.signing_key(), timeout_ms=500
        ) as ex,
        pytest.raises(QueryTimeout),
    ):
        ex.run(slow, ANALYST)


def test_database_errors_are_reported_for_repair(executor):
    with pytest.raises(QueryFailed) as info:
        executor.run("SELECT 1 / (store_id - store_id) FROM analytics.dim_store", ANALYST)
    assert "division by zero" in info.value.message


def test_validator_runs_before_the_database(executor):
    with pytest.raises(SQLRejected):
        executor.run("DELETE FROM analytics.fact_orders", ANALYST)


def test_executor_connects_as_the_read_only_role(executor):
    result = executor.run("SELECT count(*) AS n FROM analytics.dim_channel", ANALYST)
    assert result.rows == [[4]]
    with executor.pool.connection() as conn:
        user, read_only = conn.execute(
            "SELECT current_user, current_setting('transaction_read_only')"
        ).fetchone()
    assert (user, read_only) == ("nlq_reader", "on")
