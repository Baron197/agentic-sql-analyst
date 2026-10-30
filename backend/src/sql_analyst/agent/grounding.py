"""The grounding rule (guarantee 3): the model never types a number in an answer.

A number counts as typed when it appears in model-written text but not in the question
("top 5", "2025" are fine when the user wrote them). Figures reach the answer only through
template slots that code fills from the query result (`agent/render.py`).

The eval harness scores with these same functions (eval/metrics.py re-exports them).
"""

import re

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str | None) -> set[str]:
    return set(_NUMBER.findall(text or ""))


def typed_numbers(text: str | None, question: str) -> set[str]:
    """Numbers in `text` that do not appear in the question."""
    return numbers_in(text) - numbers_in(question)
