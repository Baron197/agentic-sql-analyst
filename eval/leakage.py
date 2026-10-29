"""Leakage guard: the few-shot library (data/examples.yaml) must not contain eval questions.

An example leaks if its question nearly matches any dev or test question (normalised text
similarity >= SIMILARITY_LIMIT) or its SQL equals a gold SQL after normalisation.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from eval.cases import SPLITS, load_cases

EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "data" / "examples.yaml"
SIMILARITY_LIMIT = 0.85


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


def normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().replace(";", " ").split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def find_leaks(examples: list[Example] | None = None) -> list[str]:
    """Human-readable descriptions of every leak (empty list = no leakage)."""
    examples = examples if examples is not None else load_examples()
    cases = [c for split in SPLITS for c in load_cases(split)]
    gold_sql = {normalize_sql(c.gold_sql): c.id for c in cases if c.gold_sql}
    leaks = []
    for ex in examples:
        for c in cases:
            score = similarity(ex.question, c.question)
            if score >= SIMILARITY_LIMIT:
                leaks.append(
                    f"{ex.id} question ~ {c.id} ({score:.2f}): {ex.question!r} vs {c.question!r}"
                )
        if ex.sql and normalize_sql(ex.sql) in gold_sql:
            leaks.append(f"{ex.id} SQL equals the gold SQL of {gold_sql[normalize_sql(ex.sql)]}")
    return leaks


def closest_matches(
    examples: list[Example] | None = None, top: int = 5
) -> list[tuple[float, str, str]]:
    """The most similar example/eval question pairs, for reporting how close the closest are."""
    examples = examples if examples is not None else load_examples()
    cases = [c for split in SPLITS for c in load_cases(split)]
    pairs = [(similarity(e.question, c.question), e.id, c.id) for e in examples for c in cases]
    return sorted(pairs, reverse=True)[:top]
