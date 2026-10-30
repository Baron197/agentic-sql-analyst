"""Scoring: execution accuracy (EX), refusals, safety, grounding, latency, cost.

EX compares the rows a system returned with the rows the gold SQL returns, as
multisets (as ordered lists when the case says order matters):
- column order and column names are ignored: gold columns are matched to predicted
  columns by their values;
- strict: the prediction has exactly the gold's columns;
- lenient: the gold's columns are a subset of the prediction's (extra columns allowed);
- relabeled (`results_match_relabeled`): lenient, and a label column may be renamed one-to-one;
- numbers are rounded to the precision of the gold column (gold 0.0430 accepts 0.04298,
  gold 3480887 accepts 3480887.43), so a total that is off by one order still fails.
"""

import statistics
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import product
from typing import Any

from sql_analyst.agent.grounding import numbers_in, typed_numbers

MAX_DECIMALS = 6


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


def _is_measure(values: list[Any]) -> bool:
    return any(_is_number(v) for v in values) and all(_is_number(v) or v is None for v in values)


def results_match_relabeled(
    gold_rows: Sequence[Sequence[Any]],
    pred_rows: Sequence[Sequence[Any]],
    *,
    order_matters: bool = False,
) -> bool:
    """Lenient EX that also accepts renamed labels (docs/DECISIONS.md D039).

    A gold label column (anything not numeric: flags, codes, names) may be matched by a
    predicted column that renames it one-to-one: `False`/`True` -> `weekday`/`weekend`,
    `app` -> `Mobile app`. Every gold measure column must still match exactly as in lenient
    EX, rows are paired by those measures, and each label must map to exactly one predicted
    value and back. A result with no measure column (a list of names) gets no relaxation.

    Blind spot: a consistent swap (weekday counts labelled "weekend" and vice versa) also
    passes, so reports list the cases that pass only under this rule for a human to check.
    """
    if results_match(gold_rows, pred_rows, order_matters=order_matters, strict=False):
        return True
    if len(gold_rows) != len(pred_rows) or not gold_rows:
        return False
    n_gold, n_pred = len(gold_rows[0]), len(pred_rows[0])
    if n_pred < n_gold:
        return False
    gold_columns = [_column(gold_rows, j) for j in range(n_gold)]
    measures = [j for j in range(n_gold) if _is_measure(gold_columns[j])]
    labels = [j for j in range(n_gold) if j not in measures]
    if not measures or not labels:
        return False

    precision = [max((_decimals(v) for v in col), default=0) for col in gold_columns]
    pred_columns = [_column(pred_rows, k) for k in range(n_pred)]

    def canon_col(values: list[Any], j: int) -> list[Any]:
        return [_canon(v, precision[j]) for v in values]

    candidates: list[list[int]] = []
    for j in range(n_gold):
        gold = canon_col(gold_columns[j], j)
        if j in measures:
            want = Counter(gold)
            cands = [k for k in range(n_pred) if Counter(canon_col(pred_columns[k], j)) == want]
        else:  # same number of distinct values, each used by as many rows
            shape = sorted(Counter(gold).values())
            cands = [
                k
                for k in range(n_pred)
                if sorted(Counter(canon_col(pred_columns[k], j)).values()) == shape
            ]
        if not cands:
            return False
        candidates.append(cands)

    for mapping in product(*candidates):
        if len(set(mapping)) != n_gold:
            continue
        if _relabel_pairs_ok(
            gold_rows, pred_rows, mapping, measures, labels, precision, order_matters
        ):
            return True
    return False


def _relabel_pairs_ok(gold_rows, pred_rows, mapping, measures, labels, precision, order_matters):
    """Pair rows by their measures, then check each label maps one-to-one."""

    def key(row, cols, mapped):
        return tuple(_canon(row[mapping[j] if mapped else j], precision[j]) for j in cols)

    if order_matters:
        pairs = list(zip(gold_rows, pred_rows, strict=True))
        if any(key(g, measures, False) != key(p, measures, True) for g, p in pairs):
            return False
    else:
        pool: dict[tuple, list] = {}
        for p in pred_rows:
            pool.setdefault(key(p, measures, True), []).append(p)
        pairs = []
        for g in gold_rows:
            bucket = pool.get(key(g, measures, False))
            if not bucket:
                return False
            pairs.append((g, bucket.pop()))
    for j in labels:
        forward: dict[Any, Any] = {}
        backward: dict[Any, Any] = {}
        for g, p in pairs:
            gv, pv = _canon(g[j], precision[j]), _canon(p[mapping[j]], precision[j])
            if forward.setdefault(gv, pv) != pv or backward.setdefault(pv, gv) != gv:
                return False
    return True


# ------------------------------------------------------------------- grounding
# One definition shared with the agent's render step: see sql_analyst/agent/grounding.py.
# The baseline's free-text answers violate it whenever they quote a figure; the agent is
# scored on the text its model typed (the answer template without its slots).
__all__ = ["numbers_in", "typed_numbers"]


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
