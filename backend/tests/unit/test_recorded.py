"""Recorded live runs (D048): what gets published, merging, and the generated page."""

import pytest

from sql_analyst import recorded


def record(run_id: str = "r1", keyless: bool = False, **changes) -> dict:
    """A stored run as `AgentResult.record()` writes it, private fields included."""
    base = {
        "run_id": run_id,
        "created_at": "2026-11-02T14:05:00+07:00",
        "question": "What was net revenue by sales channel in Q1 2026?",
        "user_id": "analyst@demo",
        "session_id": "a1b2c3",
        "role": "analyst",
        "lang": "en",
        "status": "answered",
        "answer": "In Q1 2026, Physical store brought in the most (IDR 9.29B).",
        "answer_template": "In Q1 2026, {r0.channel_name} brought in the most ({r0.net}).",
        "assumptions": ["Q1 2026 is the calendar quarter."],
        "caveats": [],
        "sql": "SELECT channel_name, net FROM analytics.x",
        "columns": ["channel_name", "net"],
        "rows": [["Physical store", 9285162700], ["Mobile | app", 3884159317.5]],
        "row_count": 2,
        "truncated": False,
        "chart": {"type": "bar", "x": "channel_name", "y": "net"},
        "refusal": None,
        "suggestions": [],
        "repairs": 0,
        "context": {"views": ["fact_orders"]},
        "llm_calls": [{"node": "generate_sql", "usage": {}}],
        "provider": "openai",
        "model": "gpt-6-luna",
        "trace": [{"node": "generate_sql", "ms": 2100.0, "note": "confidence high"}],
        "usage": {
            "llm_calls": 2,
            "input_tokens": 3000,
            "output_tokens": 300,
            "cache_read_tokens": 2000,
            "cache_write_tokens": 0,
            "cost_usd": 0.000512,
            "llm_latency_ms": 5000.0,
            "keyless": keyless,
        },
        "elapsed_ms": 6234.5,
    }
    return {**base, **changes}


def test_the_published_form_leaves_out_who_asked_and_internals():
    data = recorded.from_record(record()).model_dump()
    for private in ("user_id", "session_id", "context", "llm_calls", "answer_template"):
        assert private not in data
    assert data["usage"]["cost_usd"] == 0.00047 and data["chart"]["type"] == "bar"


def test_the_cost_is_priced_from_the_tokens_at_todays_prices():
    # 3,000 uncached input, 300 output, 2,000 cache read at gpt-6-luna prices; the stored
    # cost used older prices (D053).
    run = recorded.from_record(record(usage={**record()["usage"], "cache_write_tokens": 4_000}))
    expected = (3_000 * 0.10 + 300 * 0.50 + 2_000 * 0.01 + 4_000 * 0.125) / 1_000_000
    assert run.usage.cost_usd == pytest.approx(expected)


def test_keyless_runs_are_never_published():
    with pytest.raises(ValueError, match="keyless"):
        recorded.from_record(record(keyless=True))


def test_add_chooses_by_id_replaces_duplicates_and_rejects_unknown_ids():
    runs = recorded.RecordedRuns()
    assert recorded.add(runs, [record("r1"), record("r2")], {"r2"}) == ["r2"]
    recorded.add(runs, [record("r2", answer="newer")])
    assert [(r.run_id, r.answer) for r in runs.runs] == [("r2", "newer")]
    with pytest.raises(ValueError, match="r9"):
        recorded.add(runs, [record("r1")], {"r9"})


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "recorded_runs.json"
    assert recorded.load(path).runs == []  # no file yet
    runs = recorded.RecordedRuns()
    recorded.add(runs, [record("late", created_at="2026-11-03T09:00:00+07:00"), record("early")])
    recorded.save(runs, path)
    assert [r.run_id for r in recorded.load(path).runs] == ["early", "late"]


def test_the_markdown_page_shows_answers_sql_rows_and_the_honesty_notes():
    runs = recorded.RecordedRuns()
    refused = record(
        "r2",
        status="refused",
        answer="I can only read data, not delete it.",
        refusal={"kind": "unsafe", "reason": "write request", "source": "guard"},
        usage={
            **record()["usage"],
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cost_usd": 0.0,
        },
        elapsed_ms=3.2,
        sql=None,
        columns=[],
        rows=[],
        row_count=0,
    )
    recorded.add(runs, [record("r1"), refused])
    page = recorded.render_markdown(runs)
    assert "Hand-picked, not a benchmark" in page and "fictional and synthetic" in page
    assert "| 9,285,162,700 |" in page and "Mobile \\| app" in page  # pipes escaped
    assert "```sql\nSELECT channel_name" in page and "$0.000470" in page
    assert "**Refused by the rule-based guard, before any model call:** I can only read" in page
    assert "| refused | no model call | 3 ms | $0.000000 |" in page  # not the model's run
    assert "no model call (live, `gpt-6-luna` configured) · 3 ms" in page
    assert "analyst@demo" not in page
    assert "_No runs recorded yet._" in recorded.render_markdown(recorded.RecordedRuns())
