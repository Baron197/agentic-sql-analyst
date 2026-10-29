"""The golden set and the few-shot library: structure, coverage, and no leakage. No database."""

from collections import Counter

import pytest

from eval.cases import SPLITS, load_cases
from eval.leakage import Example, find_leaks, load_examples
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.validator import SQLValidator

CATEGORIES = {
    "lookup", "aggregation", "join", "time", "metric_definition",
    "ambiguous", "unanswerable", "adversarial", "access_control",
}  # fmt: skip
CASES = {split: load_cases(split) for split in SPLITS}
VALIDATOR = SQLValidator(load_dictionary())


def test_split_sizes():
    assert 35 <= len(CASES["dev"]) <= 45
    assert 55 <= len(CASES["test"]) <= 65


@pytest.mark.parametrize("split", SPLITS)
def test_every_category_and_both_users_are_covered(split):
    cases = CASES[split]
    assert {c.category for c in cases} == CATEGORIES
    assert {c.user for c in cases} == {"analyst", "manager_jakarta"}
    assert {c.expected for c in cases} == {
        "answer",
        "refuse_unsafe",
        "refuse_unanswerable",
        "state_assumption",
    }


def test_about_a_fifth_of_questions_are_indonesian():
    langs = Counter(c.lang for split in SPLITS for c in CASES[split])
    share = langs["id"] / sum(langs.values())
    assert 0.15 <= share <= 0.35, share


def test_ids_are_unique_across_splits():
    ids = [c.id for split in SPLITS for c in CASES[split]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "case", [c for s in SPLITS for c in CASES[s] if c.gold_sql], ids=lambda c: c.id
)
def test_every_gold_sql_passes_the_validator(case):
    VALIDATOR.validate(case.gold_sql)


@pytest.mark.parametrize("example", [e for e in load_examples() if e.sql], ids=lambda e: e.id)
def test_every_example_sql_passes_the_validator(example):
    VALIDATOR.validate(example.sql)


def test_no_example_leaks_an_eval_question():
    assert find_leaks() == []


def test_leakage_guard_catches_planted_duplicates():
    test_case = CASES["test"][0]
    gold = next(c for c in CASES["dev"] if c.gold_sql)
    planted = [
        Example(
            id="x1",
            question=test_case.question.upper() + "!",
            lang="en",
            decision="refuse_unanswerable",
        ),
        Example(
            id="x2",
            question="A completely different wording here",
            lang="en",
            decision="answer",
            sql=gold.gold_sql.upper(),
        ),
    ]
    leaks = find_leaks(planted)
    assert any(leak.startswith("x1 question") for leak in leaks)
    assert any(leak.startswith("x2 SQL") for leak in leaks)
