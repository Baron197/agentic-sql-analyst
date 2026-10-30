"""EX comparison and the other metric helpers. No database."""

from datetime import date, datetime
from decimal import Decimal

from eval.metrics import (
    mean_std,
    percentile,
    results_match,
    results_match_relabeled,
    typed_numbers,
)


def test_row_order_and_column_order_are_ignored():
    gold = [["app", Decimal("10")], ["web", Decimal("20")]]
    pred = [[20, "web"], [10, "app"]]
    assert results_match(gold, pred)


def test_order_matters_when_the_case_says_so():
    gold = [["a"], ["b"]]
    assert not results_match(gold, [["b"], ["a"]], order_matters=True)
    assert results_match(gold, [["a"], ["b"]], order_matters=True)


def test_strict_needs_the_same_columns_lenient_allows_extra():
    gold = [["Senayan"]]
    pred = [["Senayan", 1482]]
    assert not results_match(gold, pred, strict=True)
    assert results_match(gold, pred, strict=False)


def test_missing_gold_column_fails_even_when_lenient():
    assert not results_match([["Senayan", 1482]], [["Senayan"]], strict=False)


def test_numbers_are_rounded_to_gold_precision():
    assert results_match([[Decimal("0.0430")]], [[0.04298]])
    assert results_match([[Decimal("3480887")]], [[Decimal("3480887.43")]])
    assert results_match([[2079]], [[2079.0]])


def test_an_off_by_one_total_still_fails():
    assert not results_match([[Decimal("192701374149")]], [[Decimal("192701374148")]])
    assert not results_match([[Decimal("0.0430")]], [[0.0436]])


def test_row_count_must_match():
    assert not results_match([["a"], ["b"]], [["a"]])
    assert results_match([], [])


def test_dates_and_midnight_timestamps_compare_equal():
    assert results_match([[date(2025, 11, 11)]], [[datetime(2025, 11, 11, 0, 0)]])
    assert results_match([[date(2025, 11, 11)]], [["2025-11-11"]])


def test_duplicate_values_are_counted_as_a_multiset():
    assert not results_match([["a"], ["a"]], [["a"], ["b"]])


def test_ambiguous_column_mapping_tries_every_assignment():
    gold = [[1, 2], [3, 4]]
    pred = [[2, 1], [4, 3]]
    assert results_match(gold, pred)


def test_typed_numbers_ignores_numbers_from_the_question():
    q = "Which 5 brands sold the most units in 2025?"
    assert typed_numbers("The top 5 brands in 2025 are listed.", q) == set()
    assert typed_numbers("Sales were Rp 1.2 miliar in 2025.", q) == {"1.2"}


def test_percentile_and_mean_std():
    assert percentile([10, 20, 30, 40], 0.5) == 25.0
    assert percentile([], 0.5) is None
    assert mean_std([0.5, 0.7]) == {"mean": 0.6, "std": 0.1414}
    assert mean_std([None]) == {"mean": None, "std": None}


# ---------------------------------------------------------- relabeled EX (D039)
def test_relabeled_accepts_a_one_to_one_renamed_label():
    # dev d019 (2026-10-30 live run): a weekend flag vs. words, same counts
    gold = [[False, 4009], [True, 1996]]
    pred = [["weekday", 4009], ["weekend", 1996]]
    assert not results_match(gold, pred, strict=False)
    assert results_match_relabeled(gold, pred)
    # dev d027: channel codes vs. channel names, extra columns still allowed
    gold = [["app", Decimal("136.5")], ["store", Decimal("406.3")]]
    pred = [["Mobile app", 136.5, "x"], ["Physical store", 406.3, "y"]]
    assert results_match_relabeled(gold, pred)


def test_relabeled_still_needs_every_number_to_match():
    gold = [["app", 100], ["store", 200]]
    assert not results_match_relabeled(gold, [["Mobile app", 100], ["Physical store", 201]])


def test_relabeled_needs_a_one_to_one_mapping():
    gold = [["app", "a", 1], ["web", "a", 2], ["store", "b", 3]]
    merged = [["online", "a", 1], ["online", "a", 2], ["store", "b", 3]]  # two labels -> one
    assert not results_match_relabeled(gold, merged)


def test_relabeled_gives_no_relaxation_without_a_measure_column():
    assert not results_match_relabeled([["qris"], ["card"]], [["x"], ["y"]])


def test_relabeled_respects_row_order_when_it_matters():
    gold = [["a", 3], ["b", 1]]
    assert results_match_relabeled(gold, [["A", 3], ["B", 1]], order_matters=True)
    assert not results_match_relabeled(gold, [["B", 1], ["A", 3]], order_matters=True)


def test_relabeled_blind_spot_a_consistent_swap_passes():
    """Documented limitation: reports list relaxed-only passes for a human to check."""
    gold = [[False, 4009], [True, 1996]]
    assert results_match_relabeled(gold, [["weekend", 4009], ["weekday", 1996]])
