"""Request and response bodies (BUILD_GUIDE §10)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from sql_analyst.agent.guard import MAX_QUESTION_CHARS
from sql_analyst.agent.nodes.finalize import AgentResult
from sql_analyst.agent.schemas import ChartSpec

STREAM_ROWS = 200  # rows sent in the stream's `rows` event


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class Me(BaseModel):
    user_id: str
    display_name: str
    role: str
    region_ids: list[int] | None  # None = all regions


class DemoUser(BaseModel):
    key: str
    email: str
    role: str


class AuthOptions(BaseModel):
    demo_login_enabled: bool
    demo_users: list[DemoUser]


class DemoLoginRequest(BaseModel):
    user: Literal["analyst", "manager_jakarta"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class Usage(BaseModel):
    model: str
    keyless: bool
    llm_calls: int
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    repairs: int


class AskResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    chart: ChartSpec | None
    assumptions: list[str]
    caveats: list[str]
    refusal_reason: str | None
    suggestions: list[str]
    usage: Usage


def usage_of(r: AgentResult) -> Usage:
    u = r.usage
    return Usage(
        model=r.model,
        keyless=u.keyless,
        llm_calls=u.llm_calls,
        input_tokens=u.input_tokens + u.cache_read_tokens + u.cache_write_tokens,
        cache_read_tokens=u.cache_read_tokens,
        output_tokens=u.output_tokens,
        cost_usd=u.cost_usd,
        latency_ms=r.elapsed_ms,
        repairs=r.repairs,
    )


def ask_response(r: AgentResult) -> AskResponse:
    return AskResponse(
        run_id=r.run_id,
        status=r.status,
        answer=r.answer,
        sql=r.sql,
        columns=r.columns,
        rows=r.rows,
        row_count=r.row_count,
        truncated=r.truncated,
        chart=r.chart,
        assumptions=r.assumptions,
        caveats=r.caveats,
        refusal_reason=r.refusal.reason if r.refusal else None,
        suggestions=r.suggestions,
        usage=usage_of(r),
    )
