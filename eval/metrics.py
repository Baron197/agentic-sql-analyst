"""Scoring: execution accuracy (EX), refusals, safety, grounding, latency, cost.

EX compares the rows a system returned with the rows the gold SQL returns, as
multisets (as ordered lists when the case says order matters):
- column order and column names are ignored: gold columns are matched to predicted
  columns by their values;
- strict: the prediction has exactly the gold's columns;
- lenient: the gold's columns are a subset of the prediction's (extra columns allowed);
- numbers are rounded to the precision of the gold column (gold 0.0430 accepts 0.04298,
  gold 3480887 accepts 3480887.43), so a total that is off by one order still fails.
"""

import re
import statistics
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import product
from typing import Any

MAX_DECIMALS = 6
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


# ---------------------------------------------------------------- EX comparison
def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _to_decimal(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _decimals(v: Any) -> int:
    if not _is_number(v):
        return 0
    try:
        exp = _to_decimal(v).normalize().as_tuple().exponent
    except InvalidOperation:
        return 0
    return min(MAX_DECIMALS, max(0, -exp)) if isinstance(exp, int) else 0


def _canon(v: Any, decimals: int) -> Any:
    """A hashable, comparable form of one cell, rounded to `decimals` if numeric."""
    if v is None or isinstance(v, bool):
        return v
    if _is_number(v):
        try:
            return _to_decimal(v).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return _to_decimal(v)
    if isinstance(v, datetime):
        if v.tzinfo is None and v.time() == time(0):
            return v.date().isoformat()
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _column(rows: Sequence[Sequence[Any]], i: int) -> list[Any]:
    return [r[i] for r in rows]


def results_match(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    order_matters: bool = False,
    strict: bool = True,
) -> bool:
    """True if the predicted rows equal the gold rows under the rules in the module docstring."""
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True
    n_gold, n_pred = len(gold_rows[0]), len(pred_rows[0])
    if n_pred < n_gold or (strict and n_pred != n_gold):
        return False

    precision = [
        max((_decimals(v) for v in _column(gold_rows, j)), default=0) for j in range(n_gold)
    ]
    gold_cols = [
        Counter(_canon(v, precision[j]) for v in _column(gold_rows, j)) for j in range(n_gold)
    ]
    # Candidate predicted columns for each gold column: same multiset of values.
    candidates = []
    for j in range(n_gold):
        cands = [
            k
            for k in range(n_pred)
            if Counter(_canon(v, precision[j]) for v in _column(pred_rows, k)) == gold_cols[j]
        ]
        if not cands:
            return False
        candidates.append(cands)

    gold_canon = [tuple(_canon(r[j], precision[j]) for j in range(n_gold)) for r in gold_rows]
    gold_key = gold_canon if order_matters else Counter(gold_canon)
    for mapping in product(*candidates):
        if len(set(mapping)) != n_gold:
            continue
        pred_canon = [
            tuple(_canon(r[k], precision[j]) for j, k in enumerate(mapping)) for r in pred_rows
        ]
        if (pred_canon if order_matters else Counter(pred_canon)) == gold_key:
            return True
    return False


# ------------------------------------------------------------------- grounding
def numbers_in(text: str) -> set[str]:
    return set(_NUMBER.findall(text or ""))


def typed_numbers(answer: str, question: str) -> set[str]:
    """Numbers written in the answer that do not appear in the question.

    The project's grounding rule (guarantee 3): any such number was typed by the model
    rather than filled in by code. Free-text answers (the baseline) violate it whenever
    they quote a figure; the agent (Phase 4) fills figures from a template instead.
    """
    return numbers_in(answer) - numbers_in(question)


# ------------------------------------------------------------------ aggregates
def rate(flags: Sequence[bool]) -> float | None:
    return round(sum(flags) / len(flags), 4) if flags else None


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 1)


def mean_std(values: Sequence[float | None]) -> dict[str, float | None]:
    present = [v for v in values if v is not None]
    if not present:
        return {"mean": None, "std": None}
    std = statistics.stdev(present) if len(present) > 1 else 0.0
    return {"mean": round(statistics.fmean(present), 4), "std": round(std, 4)}
