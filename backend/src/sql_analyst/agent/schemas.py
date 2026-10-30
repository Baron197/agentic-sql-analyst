"""Structured outputs the agent asks the model for (one schema per LLM node)."""

from typing import Literal

from pydantic import BaseModel, Field


class SQLDraft(BaseModel):
    """generate_sql: one query, or a refusal."""

    decision: Literal["answer", "refuse_unsafe", "refuse_unanswerable"] = Field(
        description="answer = write SQL; refuse_unsafe = the request asks to change data, "
        "reveal personal data, or bypass security; refuse_unanswerable = the data cannot "
        "answer it, or it is not a question about the company's data"
    )
    sql: str | None = Field(
        default=None, description="One PostgreSQL SELECT query when decision=answer"
    )
    tables_used: list[str] = Field(
        default_factory=list, description="The analytics views the query reads"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Interpretations you chose for ambiguous parts of the question",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium", description="How sure you are that the query answers the question"
    )
    reason: str | None = Field(default=None, description="Short reason when refusing")


class ChartSpec(BaseModel):
    type: Literal["kpi", "bar", "line", "table"] = Field(
        description="kpi = one number; bar = category + measure; line = date + measure; "
        "table = anything else"
    )
    x: str | None = Field(default=None, description="Result column for the x axis")
    y: str | None = Field(default=None, description="Result column for the value")


class AnswerDraft(BaseModel):
    """write_answer: a template whose slots code fills from the result."""

    template: str = Field(
        description="One to three sentences in the language of the question. Every value "
        "from the result is a slot such as {{r0.net_revenue_idr}}, {{sum.orders}} or "
        "{{row_count}}. Never type a digit yourself."
    )
    chart: ChartSpec
    caveats: list[str] = Field(
        default_factory=list,
        description="Short notes the reader should know (no digits), e.g. the result was "
        "truncated or an interpretation was needed",
    )


class CriticVerdict(BaseModel):
    """check_result (optional critic): does the result answer the question?"""

    ok: bool
    problem: str | None = Field(
        default=None, description="When ok=false: what is wrong and how to fix the SQL"
    )


class GuardVerdict(BaseModel):
    """guard_input (optional classifier)."""

    category: Literal["answerable", "write_request", "personal_data", "off_topic", "unanswerable"]
    reason: str | None = None
