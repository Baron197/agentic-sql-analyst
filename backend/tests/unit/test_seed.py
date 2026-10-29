"""The seed must be deterministic and internally consistent, without a database."""

import os
import subprocess
import sys

import pytest

from sql_analyst.db.seed import generate
from sql_analyst.db.seed.ops import INJECTION_SUBJECT

SMALL = 0.05
_DIGEST = (
    "import hashlib; from sql_analyst.db.seed import generate; "
    "print(hashlib.sha256(''.join(t.digest() for t in generate(scale={scale})).encode()).hexdigest())"
)


def _digest_in_subprocess(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    out = subprocess.run(
        [sys.executable, "-c", _DIGEST.format(scale=SMALL)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_generation_is_identical_across_processes_and_hash_seeds():
    """Two fresh interpreters with different string-hash seeds must produce the same rows."""
    assert _digest_in_subprocess("1") == _digest_in_subprocess("2")


@pytest.fixture(scope="module")
def tables():
    return {t.name: t for t in generate(scale=SMALL)}


def test_every_row_matches_its_column_count(tables):
    for t in tables.values():
        assert t.rows, f"{t.name} is empty"
        assert {len(r) for r in t.rows} == {len(t.columns)}, t.name


def test_order_totals_equal_their_lines(tables):
    lines: dict[int, int] = {}
    cols = tables["order_items"].columns
    oid, qty, price, disc = (
        cols.index(c) for c in ("order_id", "quantity", "unit_price_idr", "discount_idr")
    )
    for r in tables["order_items"].rows:
        lines[r[oid]] = lines.get(r[oid], 0) + r[qty] * r[price] - r[disc]
    ocols = tables["orders"].columns
    for r in tables["orders"].rows:
        assert r[ocols.index("total_amount")] == lines[r[ocols.index("order_id")]]


def test_cancelled_orders_have_no_returns_or_shipments(tables):
    ocols = tables["orders"].columns
    cancelled = {r[0] for r in tables["orders"].rows if r[ocols.index("status")] == "cancelled"}
    assert cancelled
    assert not cancelled & {r[2] for r in tables["returns"].rows}
    assert not cancelled & {r[1] for r in tables["shipments"].rows}


def test_exactly_one_planted_injection(tables):
    subjects = [r[8] for r in tables["support_tickets"].rows]
    assert subjects.count(INJECTION_SUBJECT) == 1
