"""Eval cases: the golden question set (eval/cases/dev.yaml and test.yaml).

`dev` is for tuning; `test` is only for reported numbers and must never be used for
few-shot examples or prompt tuning (CLAUDE.md, enforced by the leakage-guard test).
"""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sql_analyst.safety.scope import UserScope
from sql_analyst.users import DEMO_USERS

CASES_DIR = Path(__file__).parent / "cases"
SPLITS = ("dev", "test")

# "Today" for every eval question: the day after the data ends, so "last month" is
# September 2026 and results never depend on when the eval runs (docs/DECISIONS.md D017).
AS_OF_DATE = date(2026, 10, 1)

Category = Literal[
    "lookup", "aggregation", "join", "time", "metric_definition",
    "ambiguous", "unanswerable", "adversarial", "access_control",
]  # fmt: skip
Expected = Literal["answer", "refuse_unsafe", "refuse_unanswerable", "state_assumption"]

USERS: dict[str, UserScope] = DEMO_USERS


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[dt]\d{3}$")
    question: str = Field(min_length=8, max_length=500)
    lang: Literal["en", "id"]
    category: Category
    difficulty: Literal["easy", "medium", "hard"]
    user: Literal["analyst", "manager_jakarta"] = "analyst"
    expected: Expected
    gold_sql: str | None = None
    order_matters: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _gold_sql_matches_expectation(self) -> "EvalCase":
        needs_sql = self.expected in ("answer", "state_assumption")
        if needs_sql and not self.gold_sql:
            raise ValueError(f"{self.id}: expected={self.expected} needs gold_sql")
        if not needs_sql and self.gold_sql:
            raise ValueError(f"{self.id}: expected={self.expected} must not have gold_sql")
        if self.category == "access_control" and self.user != "manager_jakarta":
            raise ValueError(f"{self.id}: access_control cases are asked by manager_jakarta")
        return self

    @property
    def scope(self) -> UserScope:
        return USERS[self.user]


def load_cases(split: str) -> list[EvalCase]:
    if split not in SPLITS:
        raise ValueError(f"Unknown split {split!r}; use one of {SPLITS}")
    with (CASES_DIR / f"{split}.yaml").open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cases = [EvalCase.model_validate(c) for c in raw]
    prefix = split[0]
    bad = [c.id for c in cases if not c.id.startswith(prefix)]
    if bad:
        raise ValueError(f"{split}.yaml has ids from another split: {bad}")
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{split}.yaml has duplicate ids")
    return cases
