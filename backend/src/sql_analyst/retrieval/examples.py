"""The few-shot library (data/examples.yaml) and the keyless demo questions (data/demo.yaml).

Neither may contain eval questions: eval/leakage.py fails the build on near-duplicates.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from sql_analyst.dictionary.loader import REPO_ROOT

EXAMPLES_PATH = REPO_ROOT / "data" / "examples.yaml"


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str
    lang: Literal["en", "id"]
    decision: Literal["answer", "refuse_unsafe", "refuse_unanswerable"]
    sql: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _sql_iff_answer(self) -> "Example":
        if (self.decision == "answer") != bool(self.sql):
            raise ValueError(f"{self.id}: answer examples need sql; refusals must not have it")
        return self


def load_examples(path: Path = EXAMPLES_PATH) -> list[Example]:
    with path.open(encoding="utf-8") as f:
        return [Example.model_validate(e) for e in yaml.safe_load(f)]
