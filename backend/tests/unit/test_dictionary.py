"""Structural checks on data/dictionary.yaml that need no database."""

import re

from sql_analyst.dictionary.loader import load_dictionary

D = load_dictionary()


def test_view_and_column_names_are_unique():
    names = [v.name for v in D.views]
    assert len(names) == len(set(names)) == 22
    for v in D.views:
        cols = [c.name for c in v.columns]
        assert len(cols) == len(set(cols)), v.name


def test_join_paths_point_at_documented_columns():
    known = {f"{v.name}.{c.name}" for v in D.views for c in v.columns}
    for jp in D.join_paths:
        assert jp.from_ in known, jp.from_
        assert jp.to in known, jp.to


def test_glossary_has_the_six_metrics_and_reads_only_analytics():
    assert {m.name for m in D.glossary} == {
        "gross_sales", "net_revenue", "aov", "return_rate", "active_customers", "conversion_rate",
    }  # fmt: skip
    for m in D.glossary:
        schemas = set(re.findall(r"\b(\w+)\.(?:fact|dim)_\w+", m.sql))
        assert schemas == {"analytics"}, m.name
        assert m.synonyms.en and m.synonyms.id, m.name


def test_categorical_columns_and_synonyms_in_both_languages():
    assert len(D.categorical_columns()) >= 25
    for v in D.views:
        assert v.synonyms.en and v.synonyms.id, v.name


def test_deprecated_region_code_is_flagged():
    col = D.view("fact_orders").column("region_code")
    assert col.deprecated and "DEPRECATED" in col.description
