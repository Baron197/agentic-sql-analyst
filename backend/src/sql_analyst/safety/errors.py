"""Typed safety errors. Messages are written for the agent's repair loop: say what was
wrong and what is allowed, never echo secrets or internal details."""


class SafetyError(Exception):
    """Base class: a query was refused or failed safely."""

    code = "safety_error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class SQLRejected(SafetyError):
    """The validator refused the SQL before it reached the database."""

    code = "sql_rejected"


class CostLimitExceeded(SafetyError):
    """EXPLAIN estimated the query as too expensive (often an accidental cross join)."""

    code = "cost_limit"


class QueryTimeout(SafetyError):
    """The query hit the statement timeout."""

    code = "timeout"


class QueryFailed(SafetyError):
    """Postgres rejected or failed the query (syntax, types, permissions, ...)."""

    code = "query_failed"
