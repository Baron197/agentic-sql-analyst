"""Retrieval: corpus, value matching, RRF, join bridging (no database), and the pgvector index."""

import pytest

from backend.tests.agent.conftest import DICTIONARY, RETRIEVER, VALUES
from sql_analyst.retrieval.corpus import build_chunks, tokenize
from sql_analyst.retrieval.examples import load_examples
from sql_analyst.retrieval.search import _connect, _join_graph, match_values, rrf


def test_corpus_has_a_chunk_per_view_column_metric_and_example():
    chunks = build_chunks(DICTIONARY, load_examples())
    n_columns = sum(len(v.columns) for v in DICTIONARY.views)
    expected = len(DICTIONARY.views) + n_columns + len(DICTIONARY.glossary) + len(load_examples())
    assert len(chunks) == expected and len({c.id for c in chunks}) == expected
    metric = next(c for c in chunks if c.id == "metric:net_revenue")
    assert metric.payload["views"] == ["fact_order_items", "fact_orders", "fact_returns"]


def test_tokenize_splits_snake_case_and_drops_stopwords():
    assert tokenize("What is the net_revenue_idr?") == ["net_revenue_idr", "net", "revenue", "idr"]


def test_rrf_rewards_items_ranked_well_by_both_lists():
    scores = rrf([["a", "b", "c"], ["b", "a", "d"]])
    assert max(scores, key=scores.get) in {"a", "b"} and scores["a"] == scores["b"]
    assert scores["d"] < scores["c"] or scores["d"] == scores["c"]


@pytest.mark.parametrize(
    ("question", "column", "value"),
    [
        ("Sales in Jkt last month", "city_code", "JKT"),
        ("Omzet kategori elektronik", "category_name_id", "Elektronik"),
        ("Penjualan Ibu & Anak di Surabaya", "category_name_id", "Ibu & Anak"),
        (
            "When did the Gading Serpong store open?",
            "store_name",
            "Arunika Tangerang Gading Serpong",
        ),
        ("Orders paid with e-wallet", "payment_method", "ewallet"),
        ("Revenue in Jabodetabek", "region_group", "Jabodetabek"),
    ],
)
def test_value_matching(question, column, value):
    assert (column, value) in {(m.column, m.value) for m in match_values(question, VALUES)}


def test_short_phrases_need_an_exact_match_and_single_words_a_whole_value():
    matched = {m.value for m in match_values("Who are the top customers and stores?", VALUES)}
    assert "JKT" not in matched and "Arunika Tangerang Gading Serpong" not in matched


def test_join_bridging_adds_every_view_on_a_shortest_join_path():
    graph = _join_graph(DICTIONARY)
    # fact_orders reaches dim_region via the store, the customer, or the shipment destination
    assert _connect(["fact_orders", "dim_region"], graph) == [
        "fact_orders",
        "dim_customer",
        "dim_store",
        "fact_shipments",
        "dim_region",
    ]
    assert _connect(["dim_store", "dim_region"], graph) == ["dim_store", "dim_region"]


def test_search_returns_a_compact_ranked_context():
    ctx = RETRIEVER.search("What was the return rate of electronics in 2025?")
    names = [v.name for v in ctx.views]
    assert "fact_returns" in names and len(names) <= 12
    assert "return_rate" in ctx.metrics and len(ctx.examples) == 4


# ------------------------------------------------------------ pgvector (db)
@pytest.fixture(scope="module")
def db_retriever():
    from sql_analyst.config import get_settings
    from sql_analyst.retrieval.embed import make_embedder
    from sql_analyst.retrieval.search import Retriever
    from sql_analyst.safety.executor import Executor

    settings = get_settings()
    with Executor.from_settings(settings, DICTIONARY) as ex:
        yield Retriever.from_db(ex.pool, DICTIONARY, make_embedder(settings))


@pytest.mark.db
@pytest.mark.parametrize(
    ("question", "view"),
    [
        ("Berapa omzet per cabang bulan lalu?", "dim_store"),
        ("Which courier delivered the most parcels?", "fact_shipments"),
        ("Rata-rata skor kepuasan tiket dukungan", "fact_support_tickets"),
        ("How many people visited each store?", "fact_store_daily_traffic"),
    ],
)
def test_index_in_pgvector_finds_the_right_view(db_retriever, question, view):
    """Read as the agent's read-only role; multilingual embeddings handle Indonesian."""
    ctx = db_retriever.search(question)
    assert view in [v.name for v in ctx.views]


@pytest.mark.db
def test_index_covers_every_chunk_and_categorical_value(db_retriever):
    assert len(db_retriever.chunks) == len(build_chunks(DICTIONARY, load_examples()))
    columns = {(v.view, v.column) for v in db_retriever.values}
    assert columns == {c for c in DICTIONARY.categorical_columns()} - {
        ("fact_orders", "region_code")
    }
