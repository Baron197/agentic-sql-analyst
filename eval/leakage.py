"""Leakage guard: the few-shot library (data/examples.yaml) and the keyless demo questions
(data/demo.yaml) must not contain eval questions.

An example leaks if its question nearly matches any dev or test question (normalised text
similarity >= SIMILARITY_LIMIT) or its SQL equals a gold SQL after normalisation.
"""

import re
from difflib import SequenceMatcher

from eval.cases import SPLITS, load_cases
from sql_analyst.agent.keyless import load_demo
from sql_analyst.retrieval.examples import Example, load_examples

__all__ = ["Example", "demo_examples", "find_leaks", "load_examples"]

SIMILARITY_LIMIT = 0.85


def normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().replace(";", " ").split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def demo_examples() -> list[Example]:
    """The keyless demo questions in the same shape as few-shot examples."""
    return [
        Example(id=d.id, question=d.question, lang=d.lang, decision=d.expected, sql=d.sql)
        for d in load_demo()
    ]


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
